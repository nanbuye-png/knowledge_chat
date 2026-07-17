"""
Memory-based cache implementation.

使用字典存储数据，支持 TTL 过期。
适合开发/测试环境和不需要持久化的场景。
"""
import time
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from .base import BaseCache


class MemoryCache(BaseCache):
    """基于内存的缓存实现。"""

    def __init__(self):
        self._store: Dict[str, Tuple[Any, Optional[float]]] = {}

    async def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None

        value, expire_at = entry
        if expire_at is not None and time.time() > expire_at:
            # 已过期
            del self._store[key]
            return None

        return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expire_at: Optional[float] = None
        if ttl is not None:
            expire_at = time.time() + ttl

        self._store[key] = (value, expire_at)

    async def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return False

        _, expire_at = entry
        if expire_at is not None and time.time() > expire_at:
            del self._store[key]
            return False

        return True

    async def clear(self) -> None:
        self._store.clear()
        logger.debug("MemoryCache 已清空")