from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User


async def unlock_user(db: AsyncSession, user_id: int) -> User | None:
    """解锁指定用户账户。

    清除失败登录计数和锁定截止时间，供管理员操作使用。

    Args:
        db: 数据库会话
        user_id: 用户 ID

    Returns:
        更新后的 User 对象；如果用户不存在则返回 None。
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        user.failed_login_count = 0
        user.locked_until = None
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def update_user_activity(db: AsyncSession, user_id: int) -> None:
    """更新用户最后活动时间。

    供认证、聊天等业务模块调用，刷新用户在线状态时间戳。

    Args:
        db: 数据库会话
        user_id: 用户 ID
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        user.last_activity_at = datetime.now(timezone.utc)
        db.add(user)
        await db.commit()