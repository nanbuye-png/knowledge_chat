"""Prompt cache for prompt templates, using asyncio.Lock for concurrency safety."""

import asyncio
from typing import Optional

from app.schemas.prompt_template import PromptTemplateResponse


class PromptCache:
    """线程安全、异步的 PromptTemplateResponse 对象缓存。

    使用 asyncio.Lock 确保异步应用中的安全并发访问。
    """

    def __init__(self) -> None:
        self._cache: dict[str, PromptTemplateResponse] = {}
        self._lock = asyncio.Lock()

    async def get(self, name: str) -> Optional[PromptTemplateResponse]:
        """按名称获取缓存的模板。

        如果未找到则返回 None。
        """
        async with self._lock:
            return self._cache.get(name)

    async def set(self, name: str, template: PromptTemplateResponse) -> None:
        """将模板以给定名称存入缓存。"""
        async with self._lock:
            self._cache[name] = template

    async def delete(self, name: str) -> None:
        """按名称从缓存中移除模板。

        如果名称不存在则不做任何操作。
        """
        async with self._lock:
            self._cache.pop(name, None)

    async def clear(self) -> None:
        """清除缓存中的所有条目。"""
        async with self._lock:
            self._cache.clear()

    async def has(self, name: str) -> bool:
        """按名称检查模板是否存在于缓存中。"""
        async with self._lock:
            return name in self._cache


# 共享的应用级缓存实例。
# 所有消费者（PromptProvider、CRUD 服务）都引用此单一实例，
# 以便写入和读取使用相同的内存存储。
prompt_cache = PromptCache()
