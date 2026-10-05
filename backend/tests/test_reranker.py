"""Reranker 测试（Phase 1 §5.3）。

对应计划要求：
* Retrieval 负责 Recall，Reranker 负责 Precision
* Top-K 可配置
* Reranker 不可用时必须 fallback
* Reranker 服务异常不得导致整个系统不可用
* 需要记录 retrieval_candidates / reranked_candidates / final_context / reranker_latency
"""
import asyncio
import os
import sys
import types

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.services.retrieval import reranker as reranker_module  # noqa: E402
from app.services.retrieval.reranker import (  # noqa: E402
    CrossEncoderReranker,
    LexicalOverlapReranker,
    PassthroughReranker,
    RerankerError,
    RerankerService,
    RerankStatus,
    create_reranker_service,
)


def _chunk(chunk_id: str, text: str, score: float = 0.5) -> dict:
    return {
        "id": chunk_id,
        "document_id": chunk_id,
        "filename": f"{chunk_id}.md",
        "chunk_index": 0,
        "text": text,
        "score": score,
    }


# ---------------------------------------------------------------------------
# 1: 词项重叠重排器（默认实现）
# ---------------------------------------------------------------------------


class TestLexicalOverlapReranker:
    def test_reorders_by_overlap(self):
        """与查询重叠更高的 chunk 必须排到前面（Precision）。"""
        results = [
            _chunk("c1", "住院部在另一栋楼，与门诊无关"),
            _chunk("c2", "门诊时间：上午八点到十二点"),
            _chunk("c3", "挂号需要身份证"),
        ]
        reranked = asyncio.run(LexicalOverlapReranker().rerank("门诊时间", results))

        assert reranked[0]["id"] == "c2", "命中查询关键词的 chunk 应排第一"
        assert reranked[0]["rerank_score"] > reranked[-1]["rerank_score"]
        assert all(0.0 <= r["rerank_score"] <= 1.0 for r in reranked)
        print(f"[PASS] 词项重叠重排: {[(r['id'], r['rerank_score']) for r in reranked]}")

    def test_empty_inputs(self):
        assert asyncio.run(LexicalOverlapReranker().rerank("门诊", [])) == []
        results = [_chunk("c1", "无关内容")]
        assert asyncio.run(LexicalOverlapReranker().rerank("", results)) == results

    def test_stable_order_for_ties(self):
        """分数相同时保持召回顺序（不引入随机性）。"""
        results = [_chunk("c1", "无关 A"), _chunk("c2", "无关 B")]
        reranked = asyncio.run(LexicalOverlapReranker().rerank("门诊时间", results))
        assert [r["id"] for r in reranked] == ["c1", "c2"]
        assert reranked[0]["rerank_score"] == reranked[1]["rerank_score"] == 0.0
        print("[PASS] 同分保持召回顺序（稳定排序）")


# ---------------------------------------------------------------------------
# 2: Cross-encoder 重排器（模型用替身，不下载）
# ---------------------------------------------------------------------------


class _FakeCrossEncoder:
    def __init__(self, name, scores=None, error=None, load_error=None):
        self.name = name
        self.scores = scores
        self.error = error
        self.load_error = load_error
        self.calls: list[list] = []

    def predict(self, pairs, batch_size=16, **kwargs):
        self.calls.append(pairs)
        if self.error is not None:
            raise self.error
        if self.scores is not None:
            return self.scores
        # 默认：与文本长度相关，保证可控排序
        return [float(len(text)) for _, text in pairs]


def _install_fake_cross_encoder(monkeypatch, **kwargs):
    fake = _FakeCrossEncoder("fake", **kwargs)
    module = types.ModuleType("sentence_transformers")
    outer = fake

    class _CrossEncoderFactory:
        def __new__(cls, name):
            if outer.load_error is not None:
                raise outer.load_error
            return outer

    module.CrossEncoder = _CrossEncoderFactory
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(reranker_module, "_CROSS_ENCODER_CACHE", {})
    return fake


class TestCrossEncoderReranker:
    def test_scores_are_normalised_and_sorted(self, monkeypatch):
        fake = _install_fake_cross_encoder(monkeypatch, scores=[-2.0, 3.0, 0.0])
        results = [_chunk("c1", "A"), _chunk("c2", "BB"), _chunk("c3", "CCC")]

        reranked = asyncio.run(CrossEncoderReranker().rerank("查询", results))

        assert [r["id"] for r in reranked] == ["c2", "c3", "c1"]
        assert all(
            0.0 < r["rerank_score"] < 1.0 for r in reranked
        ), "sigmoid 后应落在 (0,1)"
        assert reranked[0]["rerank_raw_score"] == 3.0
        assert len(fake.calls[0]) == 3
        print(f"[PASS] cross-encoder 分数: {[r['rerank_score'] for r in reranked]}")

    def test_model_is_cached(self, monkeypatch):
        _install_fake_cross_encoder(monkeypatch)
        reranker = CrossEncoderReranker("fake-model")
        asyncio.run(reranker.rerank("q", [_chunk("c1", "内容")]))
        first = reranker_module._CROSS_ENCODER_CACHE["fake-model"]
        asyncio.run(reranker.rerank("q", [_chunk("c2", "内容")]))
        assert reranker_module._CROSS_ENCODER_CACHE["fake-model"] is first
        print("[PASS] 重排模型按名称缓存")

    def test_load_failure_raises_reranker_error(self, monkeypatch):
        _install_fake_cross_encoder(
            monkeypatch, load_error=RuntimeError("download failed")
        )
        try:
            asyncio.run(
                CrossEncoderReranker("bad-model").rerank("q", [_chunk("c1", "x")])
            )
            raise AssertionError("加载失败应抛 RerankerError")
        except AssertionError:
            raise
        except RerankerError as exc:
            assert "加载重排模型失败" in str(exc)
            print(f"[PASS] 加载失败抛 RerankerError: {str(exc)[:40]}…")

    def test_inference_failure_raises_reranker_error(self, monkeypatch):
        _install_fake_cross_encoder(monkeypatch, error=RuntimeError("cuda oom"))
        try:
            asyncio.run(CrossEncoderReranker("m").rerank("q", [_chunk("c1", "x")]))
            raise AssertionError("推理失败应抛 RerankerError")
        except AssertionError:
            raise
        except RerankerError as exc:
            assert "重排推理失败" in str(exc)
            print("[PASS] 推理失败抛 RerankerError")

    def test_empty_results_short_circuit(self, monkeypatch):
        fake = _install_fake_cross_encoder(monkeypatch)
        assert asyncio.run(CrossEncoderReranker("m").rerank("q", [])) == []
        assert fake.calls == []


# ---------------------------------------------------------------------------
# 3: RerankerService（超时 / 降级 / 指标）
# ---------------------------------------------------------------------------


class _SlowReranker(reranker_module.Reranker):
    name = "slow"

    def __init__(self, delay: float = 5.0):
        self.delay = delay
        self.calls = 0

    async def rerank(self, query, results):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return list(results)


class _ExplodingReranker(reranker_module.Reranker):
    name = "exploding"

    async def rerank(self, query, results):
        raise RuntimeError("reranker service down")


class _EmptyReranker(reranker_module.Reranker):
    name = "empty"

    async def rerank(self, query, results):
        return []


class _ReversingReranker(reranker_module.Reranker):
    name = "reversing"

    async def rerank(self, query, results):
        out = []
        for i, r in enumerate(reversed(results)):
            item = dict(r)
            item["rerank_score"] = round(1.0 - i * 0.1, 3)
            out.append(item)
        return out


class TestRerankerService:
    def test_success_records_metrics(self):
        results = [_chunk("c1", "A"), _chunk("c2", "B"), _chunk("c3", "C")]
        service = RerankerService(_ReversingReranker(), top_k=2)

        outcome = asyncio.run(service.rerank("查询", results, top_k=2))

        assert outcome.status == RerankStatus.RERANKED.value
        assert outcome.candidates_in == 3
        assert outcome.candidates_out == 2
        assert outcome.latency_ms >= 0
        assert outcome.reranker == "reversing"
        assert outcome.results[0]["id"] == "c3", "重排后顺序应变化"
        assert outcome.results[0]["rerank_score"] == 1.0
        print(f"[PASS] 重排指标: {outcome.to_dict()}")

    def test_disabled_is_passthrough(self):
        reranker = _ReversingReranker()
        service = RerankerService(reranker, enabled=False, top_k=2)

        outcome = asyncio.run(service.rerank("查询", [_chunk("c1", "A"), _chunk("c2", "B")]))

        assert outcome.status == RerankStatus.DISABLED.value
        assert [r["id"] for r in outcome.results] == ["c1", "c2"], "关闭时保持召回顺序"
        print("[PASS] 关闭重排 → 透传")

    def test_timeout_falls_back(self):
        slow = _SlowReranker(delay=5.0)
        service = RerankerService(slow, timeout=0.05, top_k=3)

        outcome = asyncio.run(
            service.rerank("查询", [_chunk("c1", "A"), _chunk("c2", "B")])
        )

        assert outcome.status == RerankStatus.FALLBACK.value
        assert outcome.error == "timeout"
        assert [r["id"] for r in outcome.results] == ["c1", "c2"]
        print("[PASS] 重排超时 → 回退召回顺序")

    def test_exception_falls_back(self):
        service = RerankerService(_ExplodingReranker(), top_k=3)

        outcome = asyncio.run(service.rerank("查询", [_chunk("c1", "A")]))

        assert outcome.status == RerankStatus.FALLBACK.value
        assert "RuntimeError" in outcome.error
        assert len(outcome.results) == 1, "异常时仍须返回可用结果"
        print(f"[PASS] 重排异常 → 回退（{outcome.error[:30]}…）")

    def test_empty_output_falls_back(self):
        service = RerankerService(_EmptyReranker(), top_k=3)
        outcome = asyncio.run(service.rerank("查询", [_chunk("c1", "A")]))
        assert outcome.status == RerankStatus.FALLBACK.value
        assert outcome.error == "重排返回空结果"
        print("[PASS] 重排空输出 → 回退")

    def test_empty_candidates_skipped(self):
        service = RerankerService(_ReversingReranker())
        outcome = asyncio.run(service.rerank("查询", []))
        assert outcome.status == RerankStatus.SKIPPED.value
        assert outcome.results == []
        assert outcome.candidates_in == 0
        print("[PASS] 无候选 → skipped")

    def test_empty_query_falls_back(self):
        service = RerankerService(_ReversingReranker())
        outcome = asyncio.run(service.rerank("   ", [_chunk("c1", "A")]))
        assert outcome.status == RerankStatus.FALLBACK.value
        assert outcome.error == "空查询"
        print("[PASS] 空查询 → 回退")

    def test_top_k_configurable(self):
        results = [_chunk(f"c{i}", f"文本{i}") for i in range(10)]
        service = RerankerService(_ReversingReranker(), top_k=3)
        assert len(asyncio.run(service.rerank("查询", results)).results) == 3

        service2 = RerankerService(_ReversingReranker(), top_k=3)
        assert len(asyncio.run(service2.rerank("查询", results, top_k=7)).results) == 7
        print("[PASS] top_k 可配置（构造参数 + 单次覆盖）")

    def test_passthrough_reranker(self):
        results = [_chunk("c1", "A"), _chunk("c2", "B")]
        assert (
            asyncio.run(PassthroughReranker().rerank("q", results))[0]["id"] == "c1"
        )
        print("[PASS] PassthroughReranker 行为正确")


# ---------------------------------------------------------------------------
# 4: 工厂（配置驱动）
# ---------------------------------------------------------------------------


class TestRerankerFactory:
    def test_disabled_by_config(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "RERANKER_ENABLED", False)
        service = create_reranker_service(settings)
        assert service.enabled is False
        assert service.name == "passthrough"
        print("[PASS] RERANKER_ENABLED=false → 透传服务")

    def test_lexical_is_default(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "RERANKER_ENABLED", True)
        monkeypatch.setattr(settings, "RERANKER_TYPE", "lexical")
        service = create_reranker_service(settings)
        assert service.enabled is True
        assert service.name == "lexical"
        print("[PASS] 默认词项重叠重排器")

    def test_cross_encoder_selected(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "RERANKER_ENABLED", True)
        monkeypatch.setattr(settings, "RERANKER_TYPE", "cross_encoder")
        service = create_reranker_service(settings)
        assert service.name == "cross_encoder"
        print("[PASS] 可切换到 cross-encoder 重排器")


# ---------------------------------------------------------------------------
# 5: 接入检索主链路
# ---------------------------------------------------------------------------


class _StubRewriter:
    async def rewrite(self, query, history=None):
        from app.services.query.models import QueryRewriteResult, RewriteStatus

        return QueryRewriteResult(
            original_query=query,
            rewritten_query=query,
            rewrite_status=RewriteStatus.SKIPPED.value,
        )


class _StubRetriever:
    def __init__(self, results):
        self.results = results
        self.calls: list[dict] = []

    async def retrieve(self, embedding, knowledge_base_id, top_k=5, query=None):
        self.calls.append({"top_k": top_k, "query": query})
        return list(self.results)


def _stub_pipeline(monkeypatch, candidates, reranker_service):
    """构造一个注入了替身的 RetrievalPipeline。

    这里显式关掉检索缓存：缓存 key 的 fingerprint 只含 top_k / 阈值 / 检索模式
    （``RetrievalCache.build_fingerprint``），**不含重排器本身**，而缓存实例是进程级
    共享的（CI 上有 Redis 时更明显）—— 于是"同一个查询、换一个重排器"的用例会互相
    命中：后一个用例读到的是前一个用例写入的重排结果（实测
    ``test_reranker_failure_*`` 拿到 ``status=reranked``、
    ``test_disabled_reranker_*`` 拿到被逆转的顺序）。
    """
    import app.services.retrieval_pipeline as pipeline_module
    from app.services.cache.retrieval_cache import RetrievalCache
    from app.services.retrieval_pipeline import RetrievalPipeline

    async def fake_embed(text):
        return [0.1, 0.2]

    monkeypatch.setattr(pipeline_module.embedding_service, "embed_query", fake_embed)

    pipeline = RetrievalPipeline()
    pipeline._rewriter = _StubRewriter()
    pipeline._retriever = _StubRetriever(candidates)
    pipeline._reranker = reranker_service
    pipeline._cache = RetrievalCache(enabled=False)
    return pipeline


class TestPipelineIntegration:
    def test_rerank_applied_and_metadata_recorded(self, monkeypatch):
        from app.core.config import settings

        candidates = [_chunk(f"c{i}", f"内容{i}", 0.9) for i in range(8)]
        service = RerankerService(_ReversingReranker(), top_k=3)
        pipeline = _stub_pipeline(monkeypatch, candidates, service)
        monkeypatch.setattr(settings, "RERANKER_CANDIDATES", 20)

        result = asyncio.run(
            pipeline.retrieve("门诊时间", knowledge_base_id=1, top_k=3)
        )

        assert result.has_results is True
        assert len(result.results) == 3, "最终 context 只保留 top_k"
        assert result.results[0]["id"] == "c7", "重排结果应进入 context"
        rerank_meta = result.metadata["rerank"]
        assert rerank_meta["status"] == "reranked"
        assert rerank_meta["candidates_in"] == 8
        assert rerank_meta["candidates_out"] == 3
        assert rerank_meta["latency_ms"] >= 0
        assert result.metadata["retrieval_candidates"] == 8
        assert result.metadata["final_context"] == 3
        print(f"[PASS] 链路重排生效: {rerank_meta}")

    def test_recall_size_expanded_when_reranker_enabled(self, monkeypatch):
        candidates = [_chunk(f"c{i}", f"内容{i}", 0.9) for i in range(3)]
        service = RerankerService(_ReversingReranker(), top_k=2)
        pipeline = _stub_pipeline(monkeypatch, candidates, service)

        from app.core.config import settings

        monkeypatch.setattr(settings, "RERANKER_CANDIDATES", 20)

        asyncio.run(pipeline.retrieve("门诊时间", knowledge_base_id=1, top_k=2))

        assert pipeline._retriever.calls[0]["top_k"] == 20, "Recall 阶段应取候选数 20"
        assert pipeline._retriever.calls[0]["query"] == "门诊时间"
        print("[PASS] Recall 候选数按 RERANKER_CANDIDATES 扩展")

    def test_reranker_failure_does_not_break_retrieval(self, monkeypatch):
        candidates = [_chunk(f"c{i}", f"内容{i}", 0.9) for i in range(4)]
        service = RerankerService(_ExplodingReranker(), top_k=2)
        pipeline = _stub_pipeline(monkeypatch, candidates, service)

        result = asyncio.run(
            pipeline.retrieve("门诊时间", knowledge_base_id=1, top_k=2)
        )

        assert result.has_results is True, "重排失败不得让问答不可用"
        assert len(result.results) == 2
        assert result.metadata["rerank"]["status"] == "fallback"
        assert "RuntimeError" in result.metadata["rerank"]["error"]
        print("[PASS] 重排服务异常 → 链路仍可用（fallback）")

    def test_disabled_reranker_keeps_recall_order(self, monkeypatch):
        candidates = [_chunk(f"c{i}", f"内容{i}", 0.9) for i in range(4)]
        service = RerankerService(_ReversingReranker(), enabled=False, top_k=2)
        pipeline = _stub_pipeline(monkeypatch, candidates, service)

        result = asyncio.run(
            pipeline.retrieve("门诊时间", knowledge_base_id=1, top_k=2)
        )

        assert [r["id"] for r in result.results] == ["c0", "c1"]
        assert result.metadata["rerank"]["status"] == "disabled"
        print("[PASS] 关闭重排时保持召回顺序")



