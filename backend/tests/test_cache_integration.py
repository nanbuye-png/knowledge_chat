"""
Sprint 29 Step 4: Cache Integration 测试

测试:
1. CacheService - Prompt Template 缓存
2. CacheService - Knowledge Config 缓存
3. CacheService - Session 信息缓存
4. Cache hit / miss
5. TTL 过期
6. invalidate 失效
7. get_or_set 方法
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.services.cache import CacheService, MemoryCache


class TestCacheService:
    """CacheService 完整测试"""

    async def _get_service(self):
        return CacheService(cache=MemoryCache())

    def test_prompt_template_cache(self):
        """Prompt Template 缓存"""
        async def run():
            svc = await self._get_service()
            tid = "pt-001"

            # Miss
            assert await svc.get_prompt_template(tid) is None

            # Set
            data = {"id": tid, "content": "test prompt", "version": 1}
            await svc.set_prompt_template(tid, data)

            # Hit
            cached = await svc.get_prompt_template(tid)
            assert cached == data
            assert cached["content"] == "test prompt"
        asyncio.run(run())
        print("[PASS] Prompt Template cache hit/miss")

    def test_prompt_template_invalidate(self):
        """Prompt Template 失效"""
        async def run():
            svc = await self._get_service()
            await svc.set_prompt_template("pt-002", {"data": "test"})
            assert await svc.get_prompt_template("pt-002") is not None
            await svc.invalidate_prompt_template("pt-002")
            assert await svc.get_prompt_template("pt-002") is None
        asyncio.run(run())
        print("[PASS] Prompt Template invalidate")

    def test_knowledge_config_cache(self):
        """Knowledge Config 缓存"""
        async def run():
            svc = await self._get_service()
            cid = "kc-001"

            assert await svc.get_knowledge_config(cid) is None

            data = {"id": cid, "chunk_size": 500, "embedding_model": "bge-small"}
            await svc.set_knowledge_config(cid, data)

            cached = await svc.get_knowledge_config(cid)
            assert cached == data
            assert cached["chunk_size"] == 500
        asyncio.run(run())
        print("[PASS] Knowledge Config cache hit/miss")

    def test_knowledge_config_invalidate(self):
        """Knowledge Config 失效"""
        async def run():
            svc = await self._get_service()
            await svc.set_knowledge_config("kc-002", {"data": "test"})
            assert await svc.get_knowledge_config("kc-002") is not None
            await svc.invalidate_knowledge_config("kc-002")
            assert await svc.get_knowledge_config("kc-002") is None
        asyncio.run(run())
        print("[PASS] Knowledge Config invalidate")

    def test_session_cache(self):
        """Session 信息缓存"""
        async def run():
            svc = await self._get_service()
            sid = "session-001"

            assert await svc.get_session(sid) is None

            data = {"id": sid, "user_id": "u1", "context": {"last_topic": "AI"}}
            await svc.set_session(sid, data)

            cached = await svc.get_session(sid)
            assert cached == data
            assert cached["user_id"] == "u1"
        asyncio.run(run())
        print("[PASS] Session cache hit/miss")

    def test_session_invalidate(self):
        """Session 失效"""
        async def run():
            svc = await self._get_service()
            await svc.set_session("session-002", {"data": "test"})
            assert await svc.get_session("session-002") is not None
            await svc.invalidate_session("session-002")
            assert await svc.get_session("session-002") is None
        asyncio.run(run())
        print("[PASS] Session invalidate")

    def test_ttl_expiry(self):
        """TTL 过期"""
        async def run():
            svc = await self._get_service()
            await svc.set_prompt_template("ttl-pt", "expire_me")
            assert await svc.get_prompt_template("ttl-pt") is not None

            # 手动操控底层 cache 将 ttl 设短
            await svc._cache.set("prompt_template:ttl-pt", "expire_me", ttl=0)
            await asyncio.sleep(0.1)
            assert await svc.get_prompt_template("ttl-pt") is None
        asyncio.run(run())
        print("[PASS] Cache TTL expiry")

    def test_get_or_set_with_data(self):
        """get_or_set - 有数据时缓存"""
        async def run():
            svc = await self._get_service()

            def fetch_data():
                return {"value": 42}

            # cache miss -> fetch -> cache
            result = await svc.get_or_set("gos:key1", fetch_data, ttl=60)
            assert result == {"value": 42}
            assert await svc._cache.get("gos:key1") == {"value": 42}
        asyncio.run(run())
        print("[PASS] get_or_set with data")

    def test_get_or_set_cached(self):
        """get_or_set - 已缓存时返回缓存值"""
        async def run():
            svc = await self._get_service()

            call_count = 0
            def fetch_data():
                nonlocal call_count
                call_count += 1
                return {"count": call_count}

            # 第一次 miss
            result1 = await svc.get_or_set("gos:key2", fetch_data, ttl=60)
            assert result1 == {"count": 1}
            assert call_count == 1

            # 第二次 hit
            result2 = await svc.get_or_set("gos:key2", fetch_data, ttl=60)
            assert result2 == {"count": 1}  # 还是第一次的值
            assert call_count == 1  # fetch 没有被调用
        asyncio.run(run())
        print("[PASS] get_or_set cached")

    def test_get_or_set_async(self):
        """get_or_set - async fetch_func"""
        async def run():
            svc = await self._get_service()

            async def async_fetch():
                await asyncio.sleep(0.01)
                return {"async": True}

            result = await svc.get_or_set("gos:async", async_fetch, ttl=30)
            assert result == {"async": True}
        asyncio.run(run())
        print("[PASS] get_or_set async fetch_func")

    def test_clear_all(self):
        """clear_all 清空"""
        async def run():
            svc = await self._get_service()
            await svc.set_prompt_template("clr-1", "a")
            await svc.set_knowledge_config("clr-2", "b")
            await svc.set_session("clr-3", "c")

            await svc.clear_all()

            assert await svc.get_prompt_template("clr-1") is None
            assert await svc.get_knowledge_config("clr-2") is None
            assert await svc.get_session("clr-3") is None
        asyncio.run(run())
        print("[PASS] CacheService clear_all")

    def test_key_prefix_structure(self):
        """Key 前缀结构"""
        from app.services.cache.cache_service import PREFIX_PROMPT_TEMPLATE, PREFIX_KNOWLEDGE_CONFIG, PREFIX_SESSION
        assert PREFIX_PROMPT_TEMPLATE == "prompt_template"
        assert PREFIX_KNOWLEDGE_CONFIG == "knowledge_config"
        assert PREFIX_SESSION == "session"
        print(f"[PASS] Key prefixes: {PREFIX_PROMPT_TEMPLATE}, {PREFIX_KNOWLEDGE_CONFIG}, {PREFIX_SESSION}")


if __name__ == "__main__":
    print("=" * 50)
    print("Sprint 29 Step 4: Cache Integration 测试")
    print("=" * 50)

    t = TestCacheService()
    t.test_prompt_template_cache()
    t.test_prompt_template_invalidate()
    t.test_knowledge_config_cache()
    t.test_knowledge_config_invalidate()
    t.test_session_cache()
    t.test_session_invalidate()
    t.test_ttl_expiry()
    t.test_get_or_set_with_data()
    t.test_get_or_set_cached()
    t.test_get_or_set_async()
    t.test_clear_all()
    t.test_key_prefix_structure()

    print("\n" + "=" * 50)
    print("所有测试通过!")
    print("=" * 50)