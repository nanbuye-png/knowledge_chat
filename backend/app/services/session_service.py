import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.timeutil import as_naive_utc, utcnow
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
    """创建用户 Session 记录。

    ``expires_at`` 统一归一到 naive UTC（审计 §6.1-4）：调用方传 aware 会把
    "库内 naive、比较 aware" 的老问题重新引回来。
    """
    session = UserSession(
        user_id=user_id,
        token_hash=_hash_token(token),
        device_info=device_info,
        ip_address=ip_address,
        expires_at=as_naive_utc(expires_at),
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
        session.revoked_at = utcnow()
        await db.commit()


async def revoke_other_sessions(
    db: AsyncSession,
    user_id: int,
    current_token: str | None,
) -> int:
    """注销该用户**除当前 token 之外**的全部活跃 Session，返回被注销数量。

    用于「改密码即踢掉其他设备」：``get_current_user`` 会拒绝 revoked 的
    Session（auth/deps.py:108-117），因此这里置了 ``revoked_at`` 的 Session
    对应的 JWT **立即失效**；而带着当前 token 的设备继续可用 —— 否则用户改完
    密码下一步请求就被 401 掉线，等于自己被踢。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        current_token: 当前请求携带的 JWT（None 表示全部注销）

    Returns:
        被注销的 Session 数量。
    """
    from loguru import logger

    current_hash = _hash_token(current_token) if current_token else None

    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )

    count = 0
    for session in result.scalars().all():
        if current_hash is not None and session.token_hash == current_hash:
            continue
        session.revoked_at = utcnow()
        count += 1

    if count:
        await db.commit()
        logger.info(f"Revoked {count} other sessions for user_id={user_id}")
    return count


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