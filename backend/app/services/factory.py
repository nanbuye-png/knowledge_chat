"""
Provider Factory - 基础设施统一工厂层。

根据 settings 中的配置，自动选择并初始化对应 Provider。

架构：
    Settings
       |
    ProviderFactory
       |
       ├── CacheFactory
       │   ├── MemoryCache (CACHE_BACKEND=memory)
       │   └── RedisCache  (CACHE_BACKEND=redis)
       │
       └── WorkerFactory
           ├── LocalWorker   (WORKER_BACKEND=local)
           └── CeleryWorker  (WORKER_BACKEND=celery, 未来)
"""
from loguru import logger

from .cache.base import BaseCache


def _get_cache_backend() -> str:
    """获取缓存后端配置，允许运行时通过环境变量覆盖。"""
    import os
    return os.getenv("CACHE_BACKEND", "memory").lower()


def _get_worker_backend() -> str:
    """获取 Worker 后端配置，允许运行时通过环境变量覆盖。"""
    import os
    return os.getenv("WORKER_BACKEND", "local").lower()


# =============================================================
# CacheFactory
# =============================================================

def create_cache() -> BaseCache:
    """根据 CACHE_BACKEND 配置创建缓存实例。

    Returns:
        BaseCache 实例（MemoryCache 或 RedisCache）

    Raises:
        ValueError: 不支持的 CACHE_BACKEND 值
    """
    backend = _get_cache_backend()

    if backend == "memory":
        from .cache.memory_cache import MemoryCache
        cache = MemoryCache()
        logger.info("CacheFactory: 创建 MemoryCache")
        return cache

    elif backend == "redis":
        from .cache.redis_client import RedisCache
        cache = RedisCache()
        logger.info("CacheFactory: 创建 RedisCache")
        return cache

    else:
        raise ValueError(
            f"不支持的 CACHE_BACKEND: '{backend}'。"
            f"仅支持 'memory' 或 'redis'。"
        )


# =============================================================
# WorkerFactory
# =============================================================

def create_worker():
    """根据 WORKER_BACKEND 配置创建 Worker 实例。

    Returns:
        Worker 实例（LocalWorker 或未来 CeleryWorker）

    Raises:
        ValueError: 不支持的 WORKER_BACKEND 值
    """
    backend = _get_worker_backend()

    if backend == "local":
        from .tasks.local_worker import LocalWorker
        worker = LocalWorker()
        logger.info("WorkerFactory: 创建 LocalWorker")
        return worker

    elif backend == "celery":
        # TODO: 实现 CeleryWorker
        raise NotImplementedError("CeleryWorker 尚未实现")

    else:
        raise ValueError(
            f"不支持的 WORKER_BACKEND: '{backend}'。"
            f"仅支持 'local' 或 'celery'(未来)。"
        )


# =============================================================
# 统一初始化入口
# =============================================================

def init_providers():
    """初始化所有基础设施 Provider。

    在应用启动时调用，确保所有 Provider 就绪。
    """
    from .cache import set_cache
    from .tasks import set_worker

    # 创建并设置 Cache
    cache = create_cache()
    set_cache(cache)

    # 创建并设置 Worker
    worker = create_worker()
    set_worker(worker)

    logger.info(
        f"Provider 初始化完成: "
        f"CACHE_BACKEND={_get_cache_backend()}, "
        f"WORKER_BACKEND={_get_worker_backend()}"
    )
