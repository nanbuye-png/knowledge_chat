"""
Redis-based cache implementation.

使用 Redis 作为缓存后端，支持 TTL 和持久化。
依赖 redis-py 库和运行中的 Redis 服务。
"""
import json
from typing import Any, Optional

from loguru import logger

from ...core.config import settings
from .base import BaseCache


class RedisCache(BaseCache):
    """基于 Redis 的缓存实现。

    使用 JSON 序列化存储值。连接失败时降级为日志警告，不中断服务。
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or settings.REDIS_URL
        self._client = None

    async def _get_client(self):
        """延迟初始化 Redis 客户端。"""
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # 验证连接
                await self._client.ping()
                logger.info(f"Redis 连接成功: {self._redis_url}")
            except Exception as e:
                logger.warning(f"Redis 连接失败，降级为模拟模式: {e}")
                self._client = None
        return self._client

    def _serialize(self, value: Any) -> str:
        return json.dumps(value, default=str, ensure_ascii=False)

    def _deserialize(self, data: str) -> Any:
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data

    async def get(self, key: str) -> Optional[Any]:
        client = await self._get_client()
        if client is None:
            return None

        try:
            data = await client.get(key)
            if data is None:
                return None
            return self._deserialize(data)
        except Exception as e:
            logger.warning(f"Redis get 失败 ({key}): {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        client = await self._get_client()
        if client is None:
            return

        try:
            data = self._serialize(value)
            if ttl is not None:
                await client.setex(key, ttl, data)
            else:
                await client.set(key, data)
        except Exception as e:
            logger.warning(f"Redis set 失败 ({key}): {e}")

    async def delete(self, key: str) -> bool:
        client = await self._get_client()
        if client is None:
            return False

        try:
            result = await client.delete(key)
            return result > 0
        except Exception as e:
            logger.warning(f"Redis delete 失败 ({key}): {e}")
            return False

    async def exists(self, key: str) -> bool:
        client = await self._get_client()
        if client is None:
            return False

        try:
            return await client.exists(key) > 0
        except Exception as e:
            logger.warning(f"Redis exists 失败 ({key}): {e}")
            return False

    async def clear(self) -> None:
        client = await self._get_client()
        if client is None:
            return

        try:
            await client.flushdb()
            logger.info("Redis 缓存已清空")
        except Exception as e:
            logger.warning(f"Redis clear 失败: {e}")