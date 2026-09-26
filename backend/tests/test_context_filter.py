"""Context Filtering 测试（Phase 1 §5.4）。

对应计划要求：
* 增加 Context Score Threshold，低于阈值的 chunk 不进入 LLM
* threshold 可配置，不硬编码
* 保留 Debug 信息，能知道哪些 Chunk 被过滤
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.services.retrieval.context_filter import (  # noqa: E402
    ContextFilter,
    ContextFilterStatus,
)


def _chunk(chunk_id: str, score: float = 0.8, rerank_score=None) -> dict:
    chunk = {
        "id": chunk_id,
        "document_id": chunk_id,
        "filename": f"{chunk_id}.md",
        "chunk_index": 0,
        "text": f"内容 {chunk_id}",
        "score": score,
    }
    if rerank_score is not None:
        chunk["rerank_score"] = rerank_score
    return chunk


# ---------------------------------------------------------------------------
# 1: 阈值行为
# ---------------------------------------------------------------------------


class TestContextFilterThreshold:
    def test_disabled_when_threshold_is_zero(self):
        chunks = [_chunk("c1", rerank_score=0.01)]
        outcome = ContextFilter(threshold=0.0).apply(chunks)

        assert outcome.status == ContextFilterStatus.DISABLED.value
        assert len(outcome.chunks) == 1, "阈值为 0 时不做过滤"
        assert outcome.filtered == []
        print("[PASS] 阈值为 0 → 不过滤")

    def test_filters_below_threshold(self):
        chunks = [
            _chunk("c1", rerank_score=0.9),
            _chunk("c2", rerank_score=0.2),
            _chunk("c3", rerank_score=0.05),
        ]
        outcome = ContextFilter(threshold=0.3).apply(chunks)

        assert outcome.status == ContextFilterStatus.APPLIED.value
        assert [c["id"] for c in outcome.chunks] == ["c1"]
        assert outcome.candidates_in == 3
        assert outcome.kept == 1
        assert {f["id"] for f in outcome.filtered} == {"c2", "c3"}
        assert outcome.filtered[0]["score"] <= 0.3
        print(f"[PASS] 阈值过滤: kept=1, filtered={len(outcome.filtered)}")

    def test_all_filtered_reports_status(self):
        chunks = [_chunk("c1", rerank_score=0.01), _chunk("c2", rerank_score=0.02)]
        outcome = ContextFilter(threshold=0.5).apply(chunks)

        assert outcome.status == ContextFilterStatus.ALL_FILTERED.value
        assert outcome.chunks == []
        assert len(outcome.filtered) == 2
        print("[PASS] 全部低于阈值 → all_filtered（供拒答判断）")

    def test_empty_candidates_skipped(self):
        outcome = ContextFilter(threshold=0.5).apply([])
        assert outcome.status == ContextFilterStatus.SKIPPED.value
        assert outcome.candidates_in == 0
        print("[PASS] 无候选 → skipped")

    def test_threshold_is_configurable(self):
        chunks = [_chunk("c1", rerank_score=0.4)]
        assert ContextFilter(threshold=0.3).apply(chunks).chunks
        assert ContextFilter(threshold=0.5).apply(chunks).chunks == []
        print("[PASS] 阈值可配置（0.3 通过 / 0.5 过滤）")


# ---------------------------------------------------------------------------
# 2: 分数来源解析
# ---------------------------------------------------------------------------


class TestScoreSource:
    def test_auto_prefers_rerank_score(self):
        chunks = [_chunk("c1", score=0.9, rerank_score=0.1)]
        outcome = ContextFilter(threshold=0.5).apply(chunks)  # auto
        assert outcome.chunks == [], "auto 应使用 rerank_score(0.1) 而非召回分(0.9)"
        assert outcome.score_source == "auto"
        print("[PASS] auto 优先使用 rerank_score")

    def test_auto_falls_back_to_retrieval_score(self):
        """Reranker 关闭/降级时没有 rerank_score，必须回退召回分（否则会误删全部）。"""
        chunks = [_chunk("c1", score=0.9)]
        outcome = ContextFilter(threshold=0.5).apply(chunks)
        assert [c["id"] for c in outcome.chunks] == ["c1"]
        print("[PASS] 缺少 rerank_score 时回退召回分")

    def test_explicit_retrieval_source(self):
        chunks = [_chunk("c1", score=0.9, rerank_score=0.05)]
        outcome = ContextFilter(threshold=0.5, score_source="retrieval").apply(chunks)
        assert outcome.score_source == "retrieval"
        assert len(outcome.chunks) == 1
        print("[PASS] 显式指定 retrieval 分数来源")

    def test_explicit_rerank_source_drops_missing(self):
        chunks = [_chunk("c1", score=0.9)]
        outcome = ContextFilter(threshold=0.5, score_source="rerank").apply(chunks)
        assert outcome.chunks == []
        assert outcome.score_source == "rerank"
        print("[PASS] 显式 rerank 来源时缺分即过滤")

    def test_missing_score_is_conservatively_kept(self):
        """完全没有分数字段时应放行并记录，避免误删。"""
        chunks = [{"id": "c1", "document_id": "c1", "filename": "a.md", "chunk_index": 0, "text": "x"}]
        outcome = ContextFilter(threshold=0.5).apply(chunks)
        assert len(outcome.chunks) == 1
        assert outcome.score_source == "none"
        print("[PASS] 无任何分数字段时保守放行并记录来源")

    def test_debug_payload_serialisable(self):
        outcome = ContextFilter(threshold=0.3).apply(
            [_chunk("c1", rerank_score=0.9), _chunk("c2", rerank_score=0.1)]
        )
        payload = outcome.to_dict()
        assert payload["status"] == "applied"
        assert payload["threshold"] == 0.3
        assert payload["filtered_count"] == 1
        assert payload["filtered"][0]["filename"] == "c2.md"
        print(f"[PASS] Debug 明细可序列化: {payload['filtered']}")


# ---------------------------------------------------------------------------
# 3: 接入检索主链路
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

    async def retrieve(self, embedding, knowledge_base_id, top_k=5, query=None):
        return list(self.results)


class _ScoreReranker:
    """按预设分数重排（便于精确控制过滤行为）。"""

    name = "stub"

    def __init__(self, scores: dict):
        self.scores = scores

    async def rerank(self, query, results):
        out = []
        for r in results:
            item = dict(r)
            item["rerank_score"] = self.scores.get(r["id"], 0.0)
            out.append(item)
        out.sort(key=lambda r: r["rerank_score"], reverse=True)
        return out


def _pipeline_with(monkeypatch, candidates, scores, threshold: float):
    import app.services.retrieval_pipeline as pipeline_module
    from app.services.retrieval.reranker import RerankerService
    from app.services.retrieval_pipeline import RetrievalPipeline

    async def fake_embed(text):
        return [0.1, 0.2]

    monkeypatch.setattr(pipeline_module.embedding_service, "embed_query", fake_embed)

    pipeline = RetrievalPipeline()
    pipeline._rewriter = _StubRewriter()
    pipeline._retriever = _StubRetriever(candidates)
    pipeline._reranker = RerankerService(_ScoreReranker(scores), top_k=5)
    pipeline._context_filter = ContextFilter(threshold=threshold, score_source="rerank")
    return pipeline


class TestPipelineContextFiltering:
    def test_filtered_chunks_do_not_reach_context(self, monkeypatch):
        candidates = [_chunk("c1", 0.9), _chunk("c2", 0.9), _chunk("c3", 0.9)]
        scores = {"c1": 0.9, "c2": 0.4, "c3": 0.05}
        pipeline = _pipeline_with(monkeypatch, candidates, scores, threshold=0.3)

        result = asyncio.run(
            pipeline.retrieve("门诊时间", knowledge_base_id=1, top_k=3)
        )

        assert result.has_results is True
        assert [r["id"] for r in result.results] == ["c1", "c2"], "c3 低于阈值不应进入上下文"
        assert "c3" not in result.context, "被过滤的 chunk 不得出现在 Context 中"
        filter_meta = result.metadata["context_filter"]
        assert filter_meta["status"] == "applied"
        assert filter_meta["kept"] == 2
        assert [f["id"] for f in filter_meta["filtered"]] == ["c3"]
        assert result.metadata["final_context"] == 2
        print(f"[PASS] 低分 chunk 未进入 Context: {filter_meta['filtered']}")

    def test_all_filtered_yields_no_results(self, monkeypatch):
        """全部低于阈值 → 无可用上下文（§5.6 拒答的判定依据）。"""
        candidates = [_chunk("c1", 0.9), _chunk("c2", 0.9)]
        scores = {"c1": 0.01, "c2": 0.02}
        pipeline = _pipeline_with(monkeypatch, candidates, scores, threshold=0.5)

        result = asyncio.run(
            pipeline.retrieve("门诊时间", knowledge_base_id=1, top_k=2)
        )

        assert result.has_results is False
        assert result.context == ""
        assert result.sources == []
        assert result.metadata["context_filter"]["status"] == "all_filtered"
        print("[PASS] 全部被过滤 → has_results=False（触发拒答路径）")

    def test_disabled_filter_keeps_everything(self, monkeypatch):
        candidates = [_chunk("c1", 0.9), _chunk("c2", 0.9)]
        scores = {"c1": 0.9, "c2": 0.01}
        pipeline = _pipeline_with(monkeypatch, candidates, scores, threshold=0.0)

        result = asyncio.run(
            pipeline.retrieve("门诊时间", knowledge_base_id=1, top_k=2)
        )

        assert len(result.results) == 2
        assert result.metadata["context_filter"]["status"] == "disabled"
        print("[PASS] 未配置阈值时不过滤")

