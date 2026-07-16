"""FastAPI Rate Limiting Dependency。

提供 `rate_limit(limit, window_seconds)` 依赖工厂，用于 API 端点限流。

限流键维度：
- 登录接口：使用客户端 IP
- 聊天/上传接口：使用 user_id + endpoint（有认证时）或 IP（无认证时）
"""

from fastapi import Depends, HTTPException, Request, status

from ..services.security.rate_limiter import rate_limiter as _limiter
from ..core.config import settings


async def _get_client_ip(request: Request) -> str:
    """获取客户端真实 IP。
    
    优先从 X-Forwarded-For 头读取，兼容反向代理场景。
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _make_rate_limit_key(request: Request, scope: str, use_user: bool = False) -> str:
    """构建限流键。

    Args:
        request: FastAPI Request 对象
        scope: 限流作用域标识（如 "login", "chat", "upload"）
        use_user: 是否加入 user_id 维度

    Returns:
        限流键字符串
    """
    import asyncio

    ip = ""
    user_id = ""

    # 尝试获取 IP
    try:
        # _get_client_ip 是 async，但在同步上下文中我们需要用另一种方式
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        elif request.client:
            ip = request.client.host
        else:
            ip = "unknown"
    except Exception:
        ip = "unknown"

    if use_user:
        # 尝试从 request.state 或 scope 获取当前用户
        try:
            # 使用 asyncio 在当前事件循环中获取用户依赖结果
            # 注意：这里需要从请求上下文中提取已认证的用户信息
            from ..auth.deps import get_current_user
            from ..storage.database import get_db
            from sqlalchemy.ext.asyncio import AsyncSession

            # 简化策略：如果有 Authorization header，使用其 hash 作为标识
            auth_header = request.headers.get("Authorization", "")
            if auth_header:
                # 用 token 前缀作为临时 user 标识
                user_id = f"u:{hash(auth_header[-20:]) % 100000}"
            else:
                user_id = ""
        except Exception:
            user_id = ""

    if use_user and user_id:
        return f"rl:{scope}:{user_id}"
    else:
        return f"rl:{scope}:{ip}"


def rate_limit(
    limit: int | None = None,
    window_seconds: int | None = None,
    scope: str = "default",
    use_user: bool = True,
):
    """限流依赖工厂函数。

    用法:
        @router.post("/login", dependencies=[Depends(rate_limit(
            limit=settings.RATE_LIMIT_LOGIN, window_seconds=60, scope="login", use_user=False
        ))])
        async def login(...):
            ...

    Args:
        limit: 窗口内最大请求数
        window_seconds: 滑动窗口秒数
        scope: 限流场景名
        use_user: 是否在 key 中加入用户维度
    """
    _limit = limit if limit is not None else settings.RATE_LIMIT_WINDOW
    _window = window_seconds if window_seconds is not None else settings.RATE_LIMIT_WINDOW

    async def _check_rate_limit(request: Request):
        key = _make_rate_limit_key(request, scope, use_user=use_user)
        if not _limiter.check(key, _limit, _window):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )

    return _check_rate_limit
