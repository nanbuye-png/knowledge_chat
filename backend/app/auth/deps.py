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


def _get_user_id_from_payload(payload: dict) -> int | None:
    """从 JWT payload 取用户 ID（非法 payload 返回 None）。"""
    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None
    try:
        return int(user_id_str)
    except (TypeError, ValueError):
        return None


async def _load_active_user(db: AsyncSession, user_id: int) -> User | None:
    """按 ID 取用户，并校验账户状态（审计 §6.1-2）。

    软删除 / 被禁用的用户一律视为**不可用**：JWT 默认 24h 有效，只验签不看
    账户状态，等于给"已停用账号"留了一整天的读写窗口。

    Returns:
        可用用户；不存在、被禁用或已软删除时返回 ``None``。
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    return user


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

    # 审计 §6.1-2（P0）：JWT 默认 24h 有效，若这里只看 token 是否合法，
    # 被软删除/禁用的用户仍能用未过期 token 读写全部业务数据。
    # 判据与登录接口一致（见 api/auth.py 的 is_active 检查与 active_user_filter）。
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )
    if user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账户不存在或已被删除",
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
    
    用于同时支持认证和未认证的端点。**不抛异常**：token 缺失/非法/账户停用
    都返回 None，交由调用方决定（例如 chat 的 _resolve_user 还要看 API Key）。
    """
    if token is None:
        return None

    try:
        payload = decode_access_token(token)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

    user_id = _get_user_id_from_payload(payload)
    if user_id is None:
        return None

    # 与 get_current_user 同一条账户状态规则（审计 §6.1-2）
    return await _load_active_user(db, user_id)