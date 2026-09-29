"""Phase 3 §5.4 检索缓存的回归测试。

为什么这些测试重要
------------------
审计 §5.4 指出 ``CacheService`` 在生产代码里**零引用** —— Redis 修好了协议、
lifespan 也调用了 bootstrap，但缓存层对业务毫无影响。本测试锁定新引入的
「检索结果缓存」的真实行为：

* 命中即跳过 embed/检索/重排（用"检索器被调用次数"直接验证）；
* key 必须区分知识库 / 查询 / 对话历史 / top_k / 阈值（不能串味）；
* 文档变化（入库完成 / 删除 / 重跑）必须让该库缓存**整体失效**；
* 缓存损坏、缓存后端报错都不能影响问答（降级为正常检索）。
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.services.cache.memory_cache import MemoryCache  # noqa: E402
from app.services.cache.retrieval_cache import (  # noqa: E402
    PREFIX_VERSION,
    RetrievalCache,
)
from app.services.citation.models import Citation  # noqa: E402
from app.services.retrieval.models import RetrievalResult  # noqa: E402


def _result(context: str = "context-A") -> RetrievalResult:
    return RetrievalResult(
        results=[{"document_id": "d1", "filename": "a.txt", "chunk_index": 0, "text": "t"}],
        context=context,
        sources=[{"document_id": "d1", "filename": "a.txt", "chunk_index": 0, "text": "t"}],
        citations=[
            Citation(document_id="d1", filename="a.txt", chunk_id=0, score=0.9, page=2)
        ],
        metadata={"retrieval_candidates": 1},
        original_query="问题",
        search_query="问题",
        rewrite_status="skipped",
        has_results=True,
    )


class TestRetrievalCacheRoundtrip:
    def test_set_get_roundtrip(self):
        cache = RetrievalCache(MemoryCache(), ttl=60)

        asyncio.run(cache.set(1, "问题", _result(), fingerprint="k5-s0.3-mhybrid"))
        got = asyncio.run(cache.get(1, "问题", fingerprint="k5-s0.3-mhybrid"))

        assert isinstance(got, RetrievalResult)
        assert got.context == "context-A"
        assert got.has_results is True
        # Citation 必须还原成对象（下游 validator 依赖属性访问）
        assert isinstance(got.citations[0], Citation)
        assert got.citations[0].page == 2
        print("[PASS] 检索缓存 set → get 完整还原 RetrievalResult（含 Citation 对象）")

    def test_key_discriminates_kb_question_history_and_params(self):
        cache = RetrievalCache(MemoryCache(), ttl=60)
        asyncio.run(cache.set(1, "问题", _result(), fingerprint="k5-s0.3-mhybrid"))

        assert asyncio.run(cache.get(2, "问题", fingerprint="k5-s0.3-mhybrid")) is None, "知识库维度"
        assert asyncio.run(cache.get(1, "另一个问题", fingerprint="k5-s0.3-mhybrid")) is None, "查询维度"
        assert asyncio.run(cache.get(1, "问题", fingerprint="k10-s0.3-mhybrid")) is None, "参数维度"
        assert (
            asyncio.run(
                cache.get(1, "问题", history_key="hist", fingerprint="k5-s0.3-mhybrid")
            )
            is None
        ), "对话历史维度（历史会改变 Query Rewrite）"
        print("[PASS] 缓存 key 区分知识库 / 查询 / 历史 / 参数")

    def test_invalidate_bumps_version_and_drops_entries(self):
        backing = MemoryCache()
        cache = RetrievalCache(backing, ttl=60)

        asyncio.run(cache.set(1, "问题", _result(), fingerprint="fp"))
        assert asyncio.run(cache.get(1, "问题", fingerprint="fp")) is not None

        asyncio.run(cache.invalidate_knowledge_base(1))
        assert asyncio.run(cache.get(1, "问题", fingerprint="fp")) is None
        assert asyncio.run(backing.get(f"{PREFIX_VERSION}:1")) == 1

        # 失效只影响该知识库
        asyncio.run(cache.set(2, "问题", _result(context="context-B"), fingerprint="fp"))
        assert asyncio.run(cache.get(2, "问题", fingerprint="fp")) is not None
        print("[PASS] invalidate_knowledge_base 只让目标知识库的缓存失效")

    def test_disabled_cache_is_noop(self):
        cache = RetrievalCache(MemoryCache(), ttl=60, enabled=False)
        asyncio.run(cache.set(1, "问题", _result(), fingerprint="fp"))
        assert asyncio.run(cache.get(1, "问题", fingerprint="fp")) is None
        print("[PASS] RETRIEVAL_CACHE_ENABLED=false 时缓存完全旁路")

    def test_corrupt_payload_is_ignored(self):
        backing = MemoryCache()
        cache = RetrievalCache(backing, ttl=60)
        key = asyncio.run(
            cache._build_key(1, "问题", history_key="", fingerprint="fp")
        )
        asyncio.run(backing.set(key, {"unexpected": "shape"}, ttl=60))

        assert asyncio.run(cache.get(1, "问题", fingerprint="fp")) is None
        # 脏条目必须被清掉，避免每次请求都踩一次
        assert asyncio.run(backing.get(key)) is None
        print("[PASS] 缓存内容损坏 → 视为 miss 并清除（不会静默变成空结果）")


# ---------------------------------------------------------------------------
# 2: 与真实 RetrievalPipeline 接线
# ---------------------------------------------------------------------------


class _FakeRewriter:
    """改写器替身：直接返回原查询，避免测试依赖 LLM。"""

    class _Outcome:
        def __init__(self, query: str):
            self.original_query = query
            self.rewritten_query = query
            self.rewrite_status = "skipped"
            self.error = ""
            self.latency_ms = 1.0

        def to_dict(self):
            return {"rewrite_status": self.rewrite_status}

    async def rewrite(self, query, history=None):
        return self._Outcome(query)


class _FakeRetriever:
    """检索器替身：记录调用次数并返回固定 chunk。"""

    def __init__(self):
        self.calls = 0

    async def retrieve(self, embedding, knowledge_base_id, top_k, query=None):
        self.calls += 1
        return [
            {
                "document_id": "doc-1",
                "filename": "手册.md",
                "chunk_index": 0,
                "text": f"第 {self.calls} 次检索的结果",
                "score": 0.9,
                "page": 1,
                "section": "第一章",
            }
        ]


class _FakeEmbeddingService:
    def __init__(self):
        self.calls = 0

    async def embed_query(self, text):
        self.calls += 1
        return [0.1] * 8


@pytest.fixture
def pipeline_env(monkeypatch):
    """可注入替身的检索管线（不加载模型、不访问 DB / 向量库）。"""
    from app.services import retrieval_pipeline as rp_module

    retriever = _FakeRetriever()
    embedder = _FakeEmbeddingService()
    cache = RetrievalCache(MemoryCache(), ttl=60)

    monkeypatch.setattr(rp_module, "embedding_service", embedder)
    pipeline = rp_module.RetrievalPipeline()
    monkeypatch.setattr(pipeline, "_retriever", retriever)
    monkeypatch.setattr(pipeline, "_rewriter", _FakeRewriter())
    monkeypatch.setattr(pipeline, "_cache", cache)
    return pipeline, retriever, embedder, cache


class TestRetrievalPipelineCache:
    def test_second_identical_query_hits_cache(self, pipeline_env):
        pipeline, retriever, embedder, _ = pipeline_env

        first = asyncio.run(
            pipeline.retrieve("什么是 RAG？", 1, top_k=5, min_score=0.3)
        )
        second = asyncio.run(
            pipeline.retrieve("什么是 RAG？", 1, top_k=5, min_score=0.3)
        )

        assert retriever.calls == 1, "第二次应命中缓存，不再打检索器"
        assert embedder.calls == 1, "命中缓存应跳过 query embedding"
        assert second.metadata.get("cache_hit") is True
        assert first.metadata.get("cache_hit") is None
        assert second.context == first.context
        print("[PASS] 第二次相同检索命中缓存（检索器/embedding 各调用 1 次）")

    def test_invalidation_forces_re_retrieval(self, pipeline_env):
        pipeline, retriever, embedder, cache = pipeline_env

        asyncio.run(pipeline.retrieve("什么是 RAG？", 1, top_k=5, min_score=0.3))
        asyncio.run(cache.invalidate_knowledge_base(1))
        again = asyncio.run(pipeline.retrieve("什么是 RAG？", 1, top_k=5, min_score=0.3))

        assert retriever.calls == 2, "缓存失效后必须重新检索"
        assert "第 2 次检索" in again.context
        print("[PASS] 知识库缓存失效后重新检索（拿到最新内容）")

    def test_different_question_is_not_confused(self, pipeline_env):
        pipeline, retriever, _, _ = pipeline_env

        asyncio.run(pipeline.retrieve("问题 A", 1, top_k=5, min_score=0.3))
        asyncio.run(pipeline.retrieve("问题 B", 1, top_k=5, min_score=0.3))

        assert retriever.calls == 2
        print("[PASS] 不同查询不会互相命中缓存")
