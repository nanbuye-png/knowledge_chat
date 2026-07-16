import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user_session import UserSession


def _hash_token(token: str) -> str:
    """对 JWT token 进行 SHA256 hash，不存储明文。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(
    db: AsyncSession,
    user_id: int,
    token: str,
    device_info: str | None = None,
    ip_address: str | None = None,
    expires_at: datetime | None = None,
) -> UserSession:
    """创建用户 Session 记录。"""
    session = UserSession(
        user_id=user_id,
        token_hash=_hash_token(token),
        device_info=device_info,
        ip_address=ip_address,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def revoke_session(db: AsyncSession, session_id: int) -> None:
    """注销指定 Session。"""
    result = await db.execute(
        select(UserSession).where(UserSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def get_user_sessions(db: AsyncSession, user_id: int) -> list[UserSession]:
    """查询用户所有 Session。"""
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == user_id)
        .order_by(UserSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_session_by_token_hash(db: AsyncSession, token_hash: str) -> UserSession | None:
    """根据 token_hash 查询 Session。"""
    result = await db.execute(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )
    return result.scalar_one_or_none()