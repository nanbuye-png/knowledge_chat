from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger

from ..services.rate_limit_service import check_rate_limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    """请求限流中间件。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        # 登录限流：rate:login:{ip}
        if path == "/api/auth/login" and request.method == "POST":
            key = f"rate:login:{client_host}"
            allowed, info = await check_rate_limit(key, limit=30, window_seconds=300)
            if not allowed:
                logger.warning(f"Rate limit exceeded for login from {client_host}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many login attempts"},
                )

        # Chat 限流：rate:chat:{user_id}
        if path.startswith("/api/chat/") and request.method == "POST":
            # 从 request state 获取 user_id（由 auth 中间件设置）
            user_id = getattr(request.state, "user_id", None)
            if user_id is not None:
                # 根据角色设置不同限制
                role = getattr(request.state, "role", "USER")
                if role == "ROOT":
                    limit = 999999  # ROOT 无限制
                elif role == "ADMIN":
                    limit = 500  # ADMIN: 500/day
                else:
                    limit = 100  # USER: 100/day

                key = f"rate:chat:{user_id}"
                allowed, info = await check_rate_limit(key, limit=limit, window_seconds=86400)
                if not allowed:
                    logger.warning(f"Rate limit exceeded for chat user_id={user_id}")
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={"detail": "Too many requests"},
                    )

        response = await call_next(request)
        return response