"""限流中间件（Phase 3 §5.4：三套实现合并为一套）。

职责边界（避免与路由级 ``Depends(rate_limit(...))`` 重复计数）：

* **本中间件**：跨端点的「每日配额」（按角色区分的 ``/api/chat/*`` 额度）与
  请求身份解析（把 JWT 中的 ``user_id`` / ``role`` 写进 ``request.state``）；
* **路由级依赖**（``core/rate_limit.py``）：单端点的「突发限额」
  （login / upload / chat / chat_stream）。

历史问题（审计 §5.4）：

1. 中间件读 ``request.state.user_id`` / ``request.state.role``，而**全仓库
   从未给它赋值** → 按用户的配额从未生效；现在中间件自己解析 JWT（不解 DB）
   并写回 state，供所有后续依赖复用。
2. 中间件自己又实现了一套 Redis ``INCR`` 限流（与 ``core/rate_limit.py``、
   ``rate_limit_service.py`` 并存）→ 现在统一走
   :func:`app.services.security.rate_limiter.check_rate_limit`。
3. 登录限流在中间件与路由依赖里各算一次（真实额度被砍半）→ 中间件不再处理
   ``/api/auth/login``，由路由依赖单独负责。
"""
from __future__ import annotations

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger

from ..core.net import client_ip
from ..services.security.rate_limiter import check_rate_limit

#: 各角色在 ``/api/chat/*`` 上的每日配额（请求数 / 天）
CHAT_DAILY_LIMITS: dict[str, int] = {
    "ROOT": 0,       # 0 = 不限制
    "ADMIN": 500,
    "USER": 100,
}
DEFAULT_CHAT_DAILY_LIMIT = 100


def parse_identity(request: Request) -> tuple[str | None, str]:
    """从 ``Authorization`` 头解析 ``(user_id, role)``（只读 JWT，不查库）。

    审计 §5.4：中间件此前依赖 ``request.state`` 里从来没人写过的字段。
    """
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None, "ANONYMOUS"

    token = header.split(" ", 1)[1].strip()
    try:
        from ..auth.jwt import decode_access_token

        payload = decode_access_token(token)
    except Exception:
        # 过期/伪造 token 交给 get_current_user 去拒绝，这里只做限流身份
        return None, "ANONYMOUS"

    user_id = payload.get("sub")
    role = str(payload.get("role") or "USER").upper()
    return (str(user_id) if user_id else None), role


class RateLimitMiddleware(BaseHTTPMiddleware):
    """请求限流中间件（用户维度每日配额）。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        request.state.request_ip = client_ip(request)

        user_id, role = parse_identity(request)
        if user_id:
            # 只在确实解析出身份时才写 state，避免把匿名请求"伪装"成已认证
            request.state.user_id = user_id
            request.state.role = role

        if user_id and path.startswith("/api/chat/") and request.method == "POST":
            limit = CHAT_DAILY_LIMITS.get(role, DEFAULT_CHAT_DAILY_LIMIT)
            if limit > 0:
                allowed, info = await check_rate_limit(
                    f"rate:chat:{user_id}", limit=limit, window_seconds=86400
                )
                if not allowed:
                    logger.warning(
                        f"每日对话配额用尽: user_id={user_id}, role={role}, info={info}"
                    )
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "code": "RATE_LIMITED",
                            "message": "今日对话次数已达上限，请明天再试。",
                        },
                    )

        return await call_next(request)
