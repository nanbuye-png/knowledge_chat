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
from dataclasses import dataclass

from loguru import logger

from ..core.config import settings
from .cache.base import BaseCache


def _get_cache_backend() -> str:
    """获取缓存后端配置。

    优先级：环境变量（便于测试 / 运行时覆盖）→ ``settings.CACHE_BACKEND``（.env）→ ``memory``。

    历史问题：本函数原先只读 ``os.getenv``，而 ``.env`` 是通过 pydantic
    ``BaseSettings`` 读入 ``settings`` 的，不会进入 ``os.environ``，
    因此 ``CACHE_BACKEND=redis`` 写了也不生效（审计 §5.4）。
    """
    import os
    env_value = os.getenv("CACHE_BACKEND")
    if env_value:
        return env_value.lower()
    return (getattr(settings, "CACHE_BACKEND", "memory") or "memory").lower()


def _get_worker_backend() -> str:
    """获取 Worker 后端配置（优先级同 :func:`_get_cache_backend`）。"""
    import os
    env_value = os.getenv("WORKER_BACKEND")
    if env_value:
        return env_value.lower()
    return (getattr(settings, "WORKER_BACKEND", "local") or "local").lower()


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


# =============================================================
# 启动自检（P0-1）
# =============================================================

@dataclass
class InfrastructureStatus:
    """启动自检结果，用于把"配置了什么 / 实际生效了什么"写进启动日志。"""

    cache_backend: str
    worker_backend: str
    cache_type: str
    worker_type: str
    redis_configured: bool
    redis_reachable: bool
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "cache_backend": self.cache_backend,
            "worker_backend": self.worker_backend,
            "cache_type": self.cache_type,
            "worker_type": self.worker_type,
            "redis_configured": self.redis_configured,
            "redis_reachable": self.redis_reachable,
            "details": self.details,
        }


async def bootstrap_infrastructure() -> InfrastructureStatus:
    """初始化基础设施 Provider，并做一次真实的自检。

    必须由应用启动流程（``main.lifespan``）调用。此前 ``init_providers()``
    只在测试里被调用，导致 ``CACHE_BACKEND=redis`` 永远不生效、
    ``CacheService`` 成为死代码（审计 §5.4）。

    自检内容：
      1. 按配置创建并注册 Cache / Worker（``init_providers``）。
      2. 探测 Redis 连通性 —— 不可达时限流会 ``fail-open``，这个事实必须
         在启动日志里可见，而不是静默降级。

    Returns:
        :class:`InfrastructureStatus`，描述实际生效的实现与 Redis 状态。
    """
    init_providers()

    from .cache import get_cache
    from .tasks import get_worker
    from ..core.redis import get_redis

    cache = get_cache()
    worker = get_worker()

    redis_client = await get_redis()
    redis_reachable = redis_client is not None

    details = ""
    if not redis_reachable:
        details = (
            f"Redis 不可达（{getattr(settings, 'REDIS_URL', '')}）："
            f"基于 Redis 的限流将 fail-open（放行），缓存将回退为进程内实现"
        )

    return InfrastructureStatus(
        cache_backend=_get_cache_backend(),
        worker_backend=_get_worker_backend(),
        cache_type=type(cache).__name__,
        worker_type=type(worker).__name__,
        redis_configured=bool(getattr(settings, "REDIS_URL", "")),
        redis_reachable=redis_reachable,
        details=details,
    )
