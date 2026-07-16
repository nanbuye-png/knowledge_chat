"""Token 黑名单服务。

提供 JWT token 撤销、黑名单查询功能。
通过 jti（JWT ID）追踪被撤销的 token，配合 get_current_user 中的
黑名单检查实现 token 即时失效。
"""

import uuid
from datetime import datetime, timezone

import jwt
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.jwt import decode_access_token
from ...core.config import settings
from ...models.token_blacklist import TokenBlacklist

ALGORITHM = "HS256"


def _extract_jti_and_user_id(token: str) -> tuple[str, int, datetime]:
    """从 JWT token 中提取 jti、user_id 和过期时间。

    Args:
        token: JWT token 字符串

    Returns:
        (jti, user_id, expires_at)

    Raises:
        jwt.InvalidTokenError: token 无效或已过期
    """
    payload = decode_access_token(token)
    jti = payload.get("jti")
    user_id_str = payload.get("sub")
    exp_timestamp = payload.get("exp")

    if jti is None:
        raise jwt.InvalidTokenError("Token missing jti claim")
    if user_id_str is None:
        raise jwt.InvalidTokenError("Token missing sub claim")

    expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) if exp_timestamp else datetime.now(timezone.utc)

    return jti, int(user_id_str), expires_at


async def revoke_token(
    db: AsyncSession,
    token: str,
    reason: str = "logout",
) -> TokenBlacklist:
    """撤销单个 JWT token，将其加入黑名单。

    Args:
        db: 数据库会话
        token: JWT token 字符串
        reason: 撤销原因（logout / disable / admin_revoke）

    Returns:
        新创建的 TokenBlacklist 记录

    Raises:
        jwt.InvalidTokenError: token 无法解析（已过期时仍可撤销，记录为 expired）
    """
    try:
        jti, user_id, expires_at = _extract_jti_and_user_id(token)
    except jwt.ExpiredSignatureError:
        # 已过期的 token 仍可撤销（记录其 jti 和信息）
        # 尝试不验证过期地解码
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[ALGORITHM],
                options={"verify_exp": False, "verify_sub": False},
            )
            jti = payload.get("jti", str(uuid.uuid4()))
            user_id = int(payload.get("sub", 0))
            expires_at = datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)
        except Exception:
            raise jwt.InvalidTokenError("Cannot decode token for revocation")

    # 检查是否已存在（幂等）
    existing = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == jti)
    )
    if existing.scalar_one_or_none() is not None:
        logger.debug(f"Token {jti[:8]}... already blacklisted, skipping")
        return existing.scalar_one()

    blacklist_entry = TokenBlacklist(
        user_id=user_id,
        jti=jti,
        token_type="access",
        expires_at=expires_at,
        reason=reason,
    )
    db.add(blacklist_entry)
    await db.commit()
    await db.refresh(blacklist_entry)

    logger.info(f"Token revoked: jti={jti[:8]}..., user_id={user_id}, reason={reason}")
    return blacklist_entry


async def is_token_revoked(db: AsyncSession, jti: str) -> bool:
    """检查指定 jti 的 token 是否已被撤销。

    Args:
        db: 数据库会话
        jti: JWT ID

    Returns:
        True 如果 token 已被撤销
    """
    result = await db.execute(
        select(TokenBlacklist.id).where(TokenBlacklist.jti == jti).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def revoke_user_tokens(
    db: AsyncSession,
    user_id: int,
    reason: str = "admin_disable",
) -> int:
    """撤销指定用户的所有 tokens（不依赖 token 值本身）。

    注意：此方法需要配合 Session 记录使用。它会查找用户的活跃 Session
    并通过 token_hash 逐条撤销。对于已独立存在的 JWT（无 Session 记录），
    撤销仅能通过未来请求时的 lru 查询实现。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        reason: 撤销原因

    Returns:
        已撤销的 Session 数量
    """
    from ...models.user_session import UserSession
    from ..session_service import revoke_session

    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    )
    sessions = result.scalars().all()

    count = 0
    for session in sessions:
        await revoke_session(db, session.id)
        count += 1

    if count > 0:
        logger.info(
            f"Revoked {count} sessions for user_id={user_id}, reason={reason}"
        )

    return count