from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .jwt import decode_access_token
from ..models.user import User
from ..models.user_session import UserSession
from ..services.session_service import get_session_by_token_hash
from ..services.auth.token_service import is_token_revoked
from ..storage.database import get_db
import jwt


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """依赖注入：提取并验证 JWT token，返回当前用户。"""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        user_id = int(user_id_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # --- Blacklist 检查（jti） ---
    jti = payload.get("jti")
    if jti and await is_token_revoked(db, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # 检查 Session 是否已被注销
    token_hash = get_session_by_token_hash.__wrapped__ if hasattr(get_session_by_token_hash, '__wrapped__') else None
    from ..services.session_service import _hash_token
    token_hash_value = _hash_token(token)
    session = await get_session_by_token_hash(db, token_hash_value)
    if session is not None and session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )

    return user


async def get_optional_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """依赖注入：如果存在则提取 JWT token，返回用户或 None。
    
    用于同时支持认证和未认证的端点。
    """
    if token is None:
        return None

    try:
        payload = decode_access_token(token)
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            return None
        user_id = int(user_id_str)

        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
        return None