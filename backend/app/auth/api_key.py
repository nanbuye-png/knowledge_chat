"""API Key Authentication — 用于程序化 API 访问。

支持两种方式传递 API Key：
1. Authorization: Bearer sk-kc-xxxx
2. X-API-Key: sk-kc-xxxx
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..services.api_key_service import verify_api_key
from ..models.user import User
from ..storage.database import get_db


async def get_api_key_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """从请求中提取并验证 API Key。

    检查 Authorization header（Bearer）和 X-API-Key header。

    Returns:
        如果 API Key 有效返回 User 对象，否则返回 None
    """
    raw_key = None

    # 尝试从 Authorization: Bearer 头获取
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        candidate = auth_header[7:].strip()
        if candidate.startswith("sk-kc"):
            raw_key = candidate

    # 尝试从 X-API-Key 头获取
    if raw_key is None:
        candidate = request.headers.get("X-API-Key", "")
        if candidate.startswith("sk-kc"):
            raw_key = candidate

    if raw_key is None:
        return None

    user = await verify_api_key(db, raw_key)
    if user is None:
        logger.warning(f"Invalid API Key attempt: prefix={raw_key[:12]}...")
        return None

    return user


async def require_api_key_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """要求 API Key 认证，失败则返回 401。"""
    user = await get_api_key_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user