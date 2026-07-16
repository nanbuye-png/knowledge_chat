try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from ..core.config import settings

_redis_client = None


async def get_redis():
    """获取 Redis 异步客户端（单例）。
    
    如果 Redis 不可用或未安装，返回 None 以支持优雅降级。
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    if not REDIS_AVAILABLE:
        return None

    try:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        # 测试连接
        await _redis_client.ping()
        return _redis_client
    except Exception:
        # Redis 不可用，返回 None
        return None


async def close_redis() -> None:
    """关闭 Redis 连接。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
