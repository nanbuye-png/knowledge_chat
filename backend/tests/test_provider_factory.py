"""
Sprint 29 Step 8: Infrastructure Provider Configuration 测试

测试:
1. Settings 的新增配置 (CACHE_BACKEND, WORKER_BACKEND, ENVIRONMENT)
2. CacheFactory - create_cache() 返回正确的实现
3. WorkerFactory - create_worker() 返回正确的实现
4. init_providers() 统一初始化
5. 不支持的 backend 抛出 ValueError
"""
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)


class TestProviderConfig:
    """Provider 配置测试"""

    def test_default_settings(self):
        """默认配置"""
        from app.core.config import Settings

        s = Settings()
        assert s.CACHE_BACKEND == "memory"
        assert s.WORKER_BACKEND == "local"
        assert s.ENVIRONMENT == "development"
        print(f"[PASS] CACHE_BACKEND={s.CACHE_BACKEND}")
        print(f"[PASS] WORKER_BACKEND={s.WORKER_BACKEND}")
        print(f"[PASS] ENVIRONMENT={s.ENVIRONMENT}")

    def test_custom_settings(self):
        """自定义配置"""
        os.environ["CACHE_BACKEND"] = "redis"
        os.environ["WORKER_BACKEND"] = "local"
        os.environ["ENVIRONMENT"] = "production"

        from app.core.config import Settings
        s = Settings()
        assert s.CACHE_BACKEND == "redis"
        assert s.WORKER_BACKEND == "local"
        assert s.ENVIRONMENT == "production"
        print(f"[PASS] Custom CACHE_BACKEND={s.CACHE_BACKEND}")
        print(f"[PASS] Custom ENVIRONMENT={s.ENVIRONMENT}")

        # 清理
        del os.environ["CACHE_BACKEND"]
        del os.environ["WORKER_BACKEND"]
        del os.environ["ENVIRONMENT"]


class TestCacheFactory:
    """CacheFactory 测试"""

    def test_create_memory_cache(self):
        """create_cache() 返回 MemoryCache"""
        os.environ["CACHE_BACKEND"] = "memory"
        from app.core.config import settings as reload_settings
        # 强制重新加载 settings
        import importlib
        import app.core.config
        importlib.reload(app.core.config)

        from app.services.factory import create_cache
        from app.services.cache.memory_cache import MemoryCache

        cache = create_cache()
        assert isinstance(cache, MemoryCache)
        print(f"[PASS] create_cache() -> MemoryCache: {type(cache).__name__}")

    def test_create_redis_cache(self):
        """create_cache() 返回 RedisCache"""
        os.environ["CACHE_BACKEND"] = "redis"
        import importlib
        import app.core.config
        importlib.reload(app.core.config)

        from app.services.factory import create_cache
        from app.services.cache.redis_client import RedisCache

        cache = create_cache()
        assert isinstance(cache, RedisCache)
        print(f"[PASS] create_cache() -> RedisCache: {type(cache).__name__}")

    def test_invalid_cache_backend(self):
        """不支持的 CACHE_BACKEND 抛出 ValueError"""
        os.environ["CACHE_BACKEND"] = "invalid_unknown"
        import importlib
        import app.core.config
        importlib.reload(app.core.config)

        from app.services.factory import create_cache
        import pytest
        try:
            create_cache()
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "CACHE_BACKEND" in str(e)
            print(f"[PASS] Invalid cache backend raises ValueError: {e}")


class TestWorkerFactory:
    """WorkerFactory 测试"""

    def test_create_local_worker(self):
        """create_worker() 返回 LocalWorker"""
        os.environ["WORKER_BACKEND"] = "local"
        import importlib
        import app.core.config
        importlib.reload(app.core.config)

        from app.services.factory import create_worker
        from app.services.tasks.local_worker import LocalWorker

        worker = create_worker()
        assert isinstance(worker, LocalWorker)
        print(f"[PASS] create_worker() -> LocalWorker: {type(worker).__name__}")

    def test_celery_not_implemented(self):
        """CeleryWorker 未实现"""
        os.environ["WORKER_BACKEND"] = "celery"
        import importlib
        import app.core.config
        importlib.reload(app.core.config)

        from app.services.factory import create_worker
        try:
            create_worker()
            assert False, "应该抛出 NotImplementedError"
        except NotImplementedError as e:
            assert "CeleryWorker" in str(e)
            print(f"[PASS] Celery not implemented: {e}")

    def test_invalid_worker_backend(self):
        """不支持的 WORKER_BACKEND 抛出 ValueError"""
        os.environ["WORKER_BACKEND"] = "invalid_unknown"
        import importlib
        import app.core.config
        importlib.reload(app.core.config)

        from app.services.factory import create_worker
        try:
            create_worker()
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "WORKER_BACKEND" in str(e)
            print(f"[PASS] Invalid worker backend raises ValueError: {e}")


class TestInitProviders:
    """init_providers 统一初始化测试"""

    def test_init_providers(self):
        """init_providers 设置全局实例"""
        os.environ["CACHE_BACKEND"] = "memory"
        os.environ["WORKER_BACKEND"] = "local"
        import importlib
        import app.core.config
        importlib.reload(app.core.config)

        # 重置全局实例
        from app.services.cache import set_cache
        from app.services.cache.memory_cache import MemoryCache
        set_cache(MemoryCache())

        from app.services.tasks import set_worker
        from app.services.tasks.local_worker import LocalWorker
        set_worker(LocalWorker())

        # 调用 init_providers
        from app.services.factory import init_providers
        init_providers()

        # 验证全局实例
        from app.services.cache import get_cache
        from app.services.cache.memory_cache import MemoryCache
        assert isinstance(get_cache(), MemoryCache)
        print(f"[PASS] init_providers cache: {type(get_cache()).__name__}")

        from app.services.tasks import get_worker, submit_task
        from app.services.tasks.local_worker import LocalWorker
        from app.services.tasks.document_task import DocumentEmbeddingTask
        assert isinstance(get_worker(), LocalWorker)

        # 验证 worker 可用
        import asyncio
        async def test():
            task = DocumentEmbeddingTask("doc-factory", "kb-factory", "factory test")
            tid = submit_task(task)
            await asyncio.sleep(0.1)
            stored = get_worker().get_task(tid)
            assert stored is not None
            return tid
        tid = asyncio.run(test())
        print(f"[PASS] init_providers worker + submit_task: {tid}")


if __name__ == "__main__":
    print("=" * 50)
    print("Sprint 29 Step 8: Provider Factory 测试")
    print("=" * 50)

    t1 = TestProviderConfig()
    t1.test_default_settings()
    t1.test_custom_settings()

    t2 = TestCacheFactory()
    t2.test_create_memory_cache()
    t2.test_create_redis_cache()
    t2.test_invalid_cache_backend()

    t3 = TestWorkerFactory()
    t3.test_create_local_worker()
    t3.test_celery_not_implemented()
    t3.test_invalid_worker_backend()

    t4 = TestInitProviders()
    t4.test_init_providers()

    print("\n" + "=" * 50)
    print("所有测试通过!")
    print("=" * 50)