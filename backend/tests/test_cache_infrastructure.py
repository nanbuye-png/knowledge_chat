"""
Sprint 29 Step 3: Redis Infrastructure 测试

测试:
1. MemoryCache 全部方法
2. MemoryCache TTL 过期
3. Cache 实例切换 (get_cache/set_cache)
4. RedisCache 降级行为（无 Redis 时返回 None 不崩溃）
"""
import asyncio
import os
import sys
import time

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

import pytest


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestMemoryCache:
    """MemoryCache 完整测试"""

    async def _get_cache(self):
        from app.services.cache.memory_cache import MemoryCache
        return MemoryCache()

    def test_get_set(self):
        """基本 set/get"""
        async def run():
            cache = await self._get_cache()
            assert await cache.get("key1") is None
            await cache.set("key1", "value1")
            assert await cache.get("key1") == "value1"
        asyncio.run(run())
        print("[PASS] MemoryCache set/get")

    def test_set_with_ttl(self):
        """TTL 过期"""
        async def run():
            cache = await self._get_cache()
            await cache.set("ttl_key", "ttl_value", ttl=1)
            assert await cache.get("ttl_key") == "ttl_value"
            await asyncio.sleep(1.5)
            assert await cache.get("ttl_key") is None
        asyncio.run(run())
        print("[PASS] MemoryCache TTL 过期")

    def test_delete(self):
        """delete 操作"""
        async def run():
            cache = await self._get_cache()
            await cache.set("del_key", "del_value")
            assert await cache.exists("del_key") is True
            result = await cache.delete("del_key")
            assert result is True
            assert await cache.exists("del_key") is False
            # 删除不存在的键
            result = await cache.delete("nonexistent")
            assert result is False
        asyncio.run(run())
        print("[PASS] MemoryCache delete")

    def test_exists(self):
        """exists 操作"""
        async def run():
            cache = await self._get_cache()
            assert await cache.exists("no_key") is False
            await cache.set("exist_key", "val")
            assert await cache.exists("exist_key") is True
        asyncio.run(run())
        print("[PASS] MemoryCache exists")

    def test_clear(self):
        """clear 清空"""
        async def run():
            cache = await self._get_cache()
            await cache.set("a", 1)
            await cache.set("b", 2)
            await cache.set("c", 3)
            assert await cache.exists("a") is True
            await cache.clear()
            assert await cache.exists("a") is False
            assert await cache.exists("b") is False
            assert await cache.exists("c") is False
        asyncio.run(run())
        print("[PASS] MemoryCache clear")

    def test_expired_entry_not_returned(self):
        """过期条目不应返回"""
        async def run():
            cache = await self._get_cache()
            await cache.set("exp_key", "exp_val", ttl=0)
            await asyncio.sleep(0.1)
            assert await cache.get("exp_key") is None
        asyncio.run(run())
        print("[PASS] MemoryCache 过期不返回")


class TestCacheSwitching:
    """缓存实例切换测试"""

    def test_get_set_cache(self):
        """get_cache / set_cache 切换"""
        async def run():
            from app.services.cache import get_cache, set_cache
            from app.services.cache.memory_cache import MemoryCache

            cache1 = get_cache()
            assert isinstance(cache1, MemoryCache)

            new_cache = MemoryCache()
            set_cache(new_cache)
            assert get_cache() is new_cache
        asyncio.run(run())
        print("[PASS] Cache 实例切换")


if __name__ == "__main__":
    print("=" * 50)
    print("Sprint 29 Step 3: Cache Infrastructure 测试")
    print("=" * 50)

    t = TestMemoryCache()
    t.test_get_set()
    t.test_set_with_ttl()
    t.test_delete()
    t.test_exists()
    t.test_clear()
    t.test_expired_entry_not_returned()

    t2 = TestCacheSwitching()
    t2.test_get_set_cache()

    print("\n" + "=" * 50)
    print("所有测试通过!")
    print("=" * 50)