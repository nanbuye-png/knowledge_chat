"""
CacheService - 应用业务缓存层。

缓存对象：
- Prompt Template（TTL 10分钟）
- Knowledge Config（TTL 10分钟）
- Session 信息（TTL 30分钟）

业务代码通过 CacheService 访问缓存，不直接操作 Redis/Memory 实例。
"""
import asyncio
from typing import Any, Callable, Optional

from loguru import logger

from .base import BaseCache

# TTL 常量（秒）
TTL_PROMPT_TEMPLATE = 600       # 10 分钟
TTL_KNOWLEDGE_CONFIG = 600      # 10 分钟
TTL_SESSION = 1800              # 30 分钟

# Key 前缀
PREFIX_PROMPT_TEMPLATE = "prompt_template"
PREFIX_KNOWLEDGE_CONFIG = "knowledge_config"
PREFIX_SESSION = "session"


class CacheService:
    """业务缓存服务，封装缓存读写逻辑。"""

    def __init__(self, cache: Optional[BaseCache] = None):
        self._cache = cache or self._get_default_cache()

    # ---- Prompt Template ----

    async def get_prompt_template(self, template_id: str) -> Optional[Any]:
        """获取 Prompt Template 缓存。"""
        key = self._build_key(PREFIX_PROMPT_TEMPLATE, template_id)
        return await self._cache.get(key)

    async def set_prompt_template(self, template_id: str, data: Any) -> None:
        """缓存 Prompt Template。"""
        key = self._build_key(PREFIX_PROMPT_TEMPLATE, template_id)
        await self._cache.set(key, data, ttl=TTL_PROMPT_TEMPLATE)

    async def invalidate_prompt_template(self, template_id: str) -> bool:
        """使 Prompt Template 缓存失效。"""
        key = self._build_key(PREFIX_PROMPT_TEMPLATE, template_id)
        return await self._cache.delete(key)

    # ---- Knowledge Config ----

    async def get_knowledge_config(self, config_id: str) -> Optional[Any]:
        """获取 Knowledge Config 缓存。"""
        key = self._build_key(PREFIX_KNOWLEDGE_CONFIG, config_id)
        return await self._cache.get(key)

    async def set_knowledge_config(self, config_id: str, data: Any) -> None:
        """缓存 Knowledge Config。"""
        key = self._build_key(PREFIX_KNOWLEDGE_CONFIG, config_id)
        await self._cache.set(key, data, ttl=TTL_KNOWLEDGE_CONFIG)

    async def invalidate_knowledge_config(self, config_id: str) -> bool:
        """使 Knowledge Config 缓存失效。"""
        key = self._build_key(PREFIX_KNOWLEDGE_CONFIG, config_id)
        return await self._cache.delete(key)

    # ---- Session 信息 ----

    async def get_session(self, session_id: str) -> Optional[Any]:
        """获取 Session 信息缓存。"""
        key = self._build_key(PREFIX_SESSION, session_id)
        return await self._cache.get(key)

    async def set_session(self, session_id: str, data: Any) -> None:
        """缓存 Session 信息。"""
        key = self._build_key(PREFIX_SESSION, session_id)
        await self._cache.set(key, data, ttl=TTL_SESSION)

    async def invalidate_session(self, session_id: str) -> bool:
        """使 Session 信息缓存失效。"""
        key = self._build_key(PREFIX_SESSION, session_id)
        return await self._cache.delete(key)

    # ---- 通用方法 ----

    async def get_or_set(
        self,
        key: str,
        fetch_func: Callable[[], Any],
        ttl: Optional[int] = None,
    ) -> Any:
        """获取缓存，不存在则通过 fetch_func 加载并缓存。

        Args:
            key: 缓存键
            fetch_func: 数据加载函数（async callable）
            ttl: 过期时间（秒），None 使用默认 TTL

        Returns:
            缓存值或 fetch_func 返回值
        """
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug(f"Cache hit: {key}")
            return cached

        logger.debug(f"Cache miss: {key}")
        if asyncio.iscoroutinefunction(fetch_func):
            value = await fetch_func()
        else:
            value = fetch_func()

        if value is not None:
            await self._cache.set(key, value, ttl=ttl)

        return value

    async def clear_all(self) -> None:
        """清空所有缓存。"""
        await self._cache.clear()
        logger.info("CacheService: 全部缓存已清空")

    @staticmethod
    def _get_default_cache():
        """延迟获取默认缓存实例，避免循环导入。"""
        from .memory_cache import MemoryCache
        return MemoryCache()

    @staticmethod
    def _build_key(prefix: str, identifier: str) -> str:
        return f"{prefix}:{identifier}"
