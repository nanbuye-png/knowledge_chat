"""API Key 服务 — 密钥生成、验证和管理。

密钥格式：sk-kc-<user_id_hex>-<random_hex>
密钥仅创建时返回一次，数据库仅存储 SHA256 hash。
"""

import hashlib
import secrets
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.api_key import ApiKey
from ..models.user import User


API_KEY_PREFIX = "sk-kc"


def _generate_raw_api_key(user_id: int) -> tuple[str, str, str]:
    """生成原始 API Key。

    格式：sk-kc-<user_id_hex(4)>-<random_hex(40)>

    Returns:
        (raw_key, key_hash, key_prefix)
    """
    user_hex = format(user_id, "04x")
    random_part = secrets.token_hex(20)  # 40 hex chars
    raw_key = f"{API_KEY_PREFIX}-{user_hex}-{random_part}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_prefix = f"{API_KEY_PREFIX}-{user_hex}"
    return raw_key, key_hash, key_prefix


def _hash_key(raw_key: str) -> str:
    """对原生 API Key 进行 SHA256 hash。"""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def create_api_key(
    db: AsyncSession,
    user_id: int,
    name: str,
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    """创建新的 API Key。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        name: Key 名称
        expires_at: 过期时间（可选）

    Returns:
        (ApiKey 对象, 明文 key) — 明文 key 仅返回一次
    """
    raw_key, key_hash, key_prefix = _generate_raw_api_key(user_id)

    api_key = ApiKey(
        user_id=user_id,
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    logger.info(f"API Key created: id={api_key.id}, user_id={user_id}, name={name}")
    return api_key, raw_key


async def verify_api_key(db: AsyncSession, raw_key: str) -> User | None:
    """验证 API Key 并返回所属用户。

    如果 key 有效，会更新 last_used_at。

    Args:
        db: 数据库会话
        raw_key: 完整 API Key 字符串

    Returns:
        如果有效返回 User 对象，否则返回 None
    """
    key_hash = _hash_key(raw_key)

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        return None

    # 检查是否激活
    if not api_key.is_active:
        return None

    # 检查是否过期
    if api_key.expires_at is not None and api_key.expires_at < datetime.now(timezone.utc):
        return None

    # 更新最后使用时间
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    # 返回用户
    user_result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()
    return user


async def revoke_api_key(db: AsyncSession, key_id: int, user_id: int) -> ApiKey | None:
    """撤销指定 API Key（软撤销，设置 is_active=False）。

    Args:
        db: 数据库会话
        key_id: API Key ID
        user_id: 用户 ID（验证所有权）

    Returns:
        更新后的 ApiKey 对象，如果不存在返回 None
    """
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        return None

    api_key.is_active = False
    await db.commit()
    await db.refresh(api_key)
    return api_key


async def delete_api_key(db: AsyncSession, key_id: int, user_id: int) -> bool:
    """物理删除 API Key。

    Args:
        db: 数据库会话
        key_id: API Key ID
        user_id: 用户 ID

    Returns:
        是否成功删除
    """
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        return False

    await db.delete(api_key)
    await db.commit()
    return True


async def get_user_api_keys(db: AsyncSession, user_id: int) -> list[ApiKey]:
    """获取用户的所有 API Key（不包含 key_hash）。

    Args:
        db: 数据库会话
        user_id: 用户 ID

    Returns:
        ApiKey 对象列表
    """
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user_id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())