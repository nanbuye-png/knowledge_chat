"""FastAPI Rate Limiting Dependency（Phase 3 §5.4）。

路由级限流依赖工厂：``dependencies=[Depends(rate_limit(...))]``。

统一到唯一实现 :func:`app.services.security.rate_limiter.check_rate_limit`
（Redis 优先、进程内滑动窗口兜底），并修正审计 §5.4 的两个问题：

1. **客户端可伪造 IP**：改为 :func:`app.core.net.client_ip`（按
   ``TRUSTED_PROXY_COUNT`` 从 X-Forwarded-For 右往左取）。
2. **键维度混乱**：用户维度优先取 ``request.state.user_id``（由
   :class:`~app.middleware.rate_limit.RateLimitMiddleware` 解析 JWT 写入），
   拿不到时退化为「token 摘要」，不再依赖 ``hash()``（Python 的字符串 hash
   每进程随机加盐，多进程下同一个用户会落到不同键上 → 限额被放大）。
"""
from __future__ import annotations

import hashlib

from fastapi import Request, status

from ..core.config import settings
from ..core.exceptions import AppError
from ..core.net import client_ip
from ..services.security.rate_limiter import check_rate_limit as _check


def _identity(request: Request, use_user: bool) -> str:
    """构建「用户维度」的标识（无认证时回退到 IP）。"""
    if not use_user:
        return f"ip:{client_ip(request)}"

    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"u:{user_id}"

    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        # 稳定的 token 摘要（sha256 前 16 位）；不再用 hash()：进程间随机盐
        digest = hashlib.sha256(auth_header[-64:].encode("utf-8")).hexdigest()[:16]
        return f"t:{digest}"

    return f"ip:{client_ip(request)}"


def _make_rate_limit_key(request: Request, scope: str, use_user: bool) -> str:
    """限流键：``rl:{scope}:{identity}``。"""
    return f"rl:{scope}:{_identity(request, use_user)}"


def rate_limit(
    limit: int | None = None,
    window_seconds: int | None = None,
    scope: str = "default",
    use_user: bool = True,
    setting: str | None = None,
    window_setting: str = "RATE_LIMIT_WINDOW",
):
    """限流依赖工厂函数。

    用法::

        @router.post("/login", dependencies=[Depends(rate_limit(
            setting="RATE_LIMIT_LOGIN", scope="login", use_user=False,
        ))])
        async def login(...):
            ...

    Args:
        limit: 窗口内最大请求数（显式值；``None`` 时读 ``setting``）。
        window_seconds: 窗口秒数（显式值；``None`` 时读 ``window_setting``）。
        scope: 限流场景名（键前缀的一部分）。
        use_user: 是否使用用户维度（False = 只用 IP）。
        setting: ``settings`` 里的限额字段名 —— **在请求时解析**，
            因此改配置/测试打补丁都能立即生效（显式传入 ``limit`` 时忽略）。
        window_setting: ``settings`` 里的窗口字段名。

    Returns:
        可直接作为 ``Depends(...)`` 使用的异步依赖。
    """

    async def _check_rate_limit(request: Request):
        effective_limit = limit
        if effective_limit is None and setting:
            effective_limit = int(getattr(settings, setting, 0))
        if effective_limit is None:
            effective_limit = int(getattr(settings, "RATE_LIMIT_WINDOW", 60))

        effective_window = window_seconds
        if effective_window is None:
            effective_window = int(getattr(settings, window_setting, 60))

        key = _make_rate_limit_key(request, scope, use_user=use_user)
        allowed, info = await _check(key, effective_limit, effective_window)
        if not allowed:
            raise AppError(
                message="请求过于频繁，请稍后再试。",
                code="RATE_LIMITED",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    return _check_rate_limit
