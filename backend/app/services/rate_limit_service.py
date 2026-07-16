from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.redis import get_redis


async def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, dict]:
    """检查请求是否超过限流阈值。

    Args:
        key: 限流 key，如 "rate:login:127.0.0.1"
        limit: 窗口内最大请求数
        window_seconds: 时间窗口（秒）

    Returns:
        (allowed, info)
        - allowed: True 表示允许，False 表示拒绝
        - info: 包含当前计数、剩余配额、重置时间等信息
    """
    redis = await get_redis()
    if redis is None:
        # Redis 不可用，允许通过
        return True, {"redis_available": False}

    now = datetime.now(timezone.utc)
    current_count = await redis.incr(key)

    if current_count == 1:
        # 首次请求，设置过期时间
        await redis.expire(key, window_seconds)

    ttl = await redis.ttl(key)
    reset_at = now.replace(tzinfo=None) + __import__('datetime').timedelta(seconds=ttl) if ttl > 0 else now

    remaining = max(0, limit - current_count)
    allowed = current_count <= limit

    info = {
        "redis_available": True,
        "current_count": current_count,
        "limit": limit,
        "remaining": remaining,
        "reset_at": reset_at.isoformat() if ttl > 0 else None,
    }

    return allowed, info