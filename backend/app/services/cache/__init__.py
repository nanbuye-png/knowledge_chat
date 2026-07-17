"""
Cache provider package.

提供缓存抽象层，支持 MemoryCache（默认）和 RedisCache。
业务代码通过 CacheService 访问缓存，不直接调用具体实现。
"""
from .base import BaseCache
from .memory_cache import MemoryCache

# 默认使用内存缓存
_cache_instance: BaseCache = MemoryCache()


def get_cache() -> BaseCache:
    """获取当前缓存实例。"""
    return _cache_instance


def set_cache(cache: BaseCache) -> None:
    """设置缓存实例（用于运行时切换或依赖注入）。"""
    global _cache_instance
    _cache_instance = cache


# CacheService 在 get_cache/set_cache 之后导入，避免循环引用
from .cache_service import CacheService  # noqa: E402


__all__ = [
    "BaseCache",
    "MemoryCache",
    "CacheService",
    "get_cache",
    "set_cache",
]