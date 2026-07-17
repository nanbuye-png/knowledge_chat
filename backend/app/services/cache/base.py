"""
Base cache interface.

所有缓存实现需继承 BaseCache 并实现以下方法：
- get(key)
- set(key, value, ttl)
- delete(key)
- exists(key)
- clear()
"""
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseCache(ABC):
    """缓存抽象基类。"""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值。不存在或已过期返回 None。"""
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值。

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 表示永不过期
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存键。返回 True 表示删除成功，False 表示键不存在。"""
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """清空所有缓存。"""
        ...