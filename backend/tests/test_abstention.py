"""Abstention / 拒答测试（Phase 1 §5.6）。

对应计划要求：
* 无足够依据时不调用 LLM，直接拒答（"不要让 LLM 猜测"）
* threshold 可配置
* 支持 Debug（能看出拒答原因与分数）
* 必须覆盖"有答案 / 无答案 / 低分结果"三类场景
"""
import asyncio
import json
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.services.retrieval.abstention import (  # noqa: E402
    AbstentionDecider,
    AbstentionReason,
    create_abstention_decider,
)
from app.services.retrieval.models import RetrievalResult  # noqa: E402


def _result(chunks=None, has_results=None) -> RetrievalResult:
    from app.services.citation.builder import CitationBuilder

    chunks = chunks or []
    if has_results is None:
        has_results = bool(chunks)
    sources = [
        {
            "document_id": c["document_id"],
            "filename": c["filename"],
            "chunk_index": c["chunk_index"],
            "text": c["text"][:200],
            "page": c.get("page"),
            "section": c.get("section"),
        }
        for c in chunks
    ]
    return RetrievalResult(
        results=chunks,
        sources=sources,
        citations=CitationBuilder().build(chunks),
        has_results=has_results,
    )


def _chunk(score: float = 0.8, rerank_score=None) -> dict:
    chunk = {
        "id": f"doc_{score}",
        "document_id": "doc",
        "filename": "doc.pdf",
        "chunk_index": 0,
        "text": "内容",
        "score": score,
    }
    if rerank_score is not None:
        chunk["rerank_score"] = rerank_score
    return chunk


# ---------------------------------------------------------------------------
# 1: 判定逻辑
# ---------------------------------------------------------------------------


class TestAbstentionDecider:
    def test_no_context_abstains(self):
        decision = AbstentionDecider().decide(_result([]))
        assert decision.should_abstain is True
        assert decision.reason == AbstentionReason.NO_CONTEXT
        assert decision.message
        print(f"[PASS] 无上下文拒答: {decision.message}")

    def test_insufficient_context_abstains(self):
        decider = AbstentionDecider(min_context_chunks=3)
        decision = decider.decide(_result([_chunk(), _chunk()]))
        assert decision.should_abstain is True
        assert decision.reason == AbstentionReason.INSUFFICIENT_CONTEXT
        assert decision.details["context_chunks"] == 2
        print("[PASS] 上下文不足拒答")

    def test_low_retrieval_score_abstains(self):
        decider = AbstentionDecider(score_threshold=0.5)
        decision = decider.decide(_result([_chunk(score=0.31), _chunk(score=0.2)]))
        assert decision.should_abstain is True
        assert decision.reason == AbstentionReason.LOW_RETRIEVAL_SCORE
        assert decision.details["best_retrieval_score"] == 0.31
        print("[PASS] 低召回分拒答（0.31 < 0.5）")

    def test_low_rerank_score_abstains(self):
        decider = AbstentionDecider(rerank_threshold=0.6)
        decision = decider.decide(
            _result([_chunk(score=0.9, rerank_score=0.2)])
        )
        assert decision.should_abstain is True
        assert decision.reason == AbstentionReason.LOW_RERANK_SCORE
        assert decision.details["best_rerank_score"] == 0.2
        print("[PASS] 低重排分拒答")

    def test_answering_path_does_not_abstain(self):
        """有足够依据时必须放行给 LLM。"""
        decider = AbstentionDecider(
            min_context_chunks=1, score_threshold=0.3, rerank_threshold=0.2
        )
        decision = decider.decide(
            _result([_chunk(score=0.8, rerank_score=0.7)])
        )
        assert decision.should_abstain is False
        assert decision.reason == ""
        assert decision.details["best_retrieval_score"] == 0.8
        print("[PASS] 有依据时放行")

    def test_disabled_never_abstains(self):
        decider = AbstentionDecider(enabled=False, score_threshold=0.99)
        decision = decider.decide(_result([_chunk(score=0.01)]))
        assert decision.should_abstain is False
        assert decision.details["enabled"] is False
        print("[PASS] 关闭拒答后不再按分数拒答（便于对照实验）")

    def test_no_context_still_abstains_when_disabled(self):
        """安全不变量：关闭拒答开关也必须阻止"空上下文调用 LLM"。"""
        decider = AbstentionDecider(enabled=False)
        decision = decider.decide(_result([]))
        assert decision.should_abstain is True
        assert decision.reason == AbstentionReason.NO_CONTEXT
        print("[PASS] 关闭开关时无上下文仍拒答（安全不变量）")

    def test_thresholds_disabled_by_default(self):
        """默认只做结构性拒答：分数不为 0 时不因分数拒答。"""
        decider = AbstentionDecider()
        assert decider.score_threshold == 0.0
        decision = decider.decide(_result([_chunk(score=0.01)]))
        assert decision.should_abstain is False
        print("[PASS] 默认不启用分数阈值拒答")

    def test_debug_details_include_pipeline_metadata(self):
        result = _result([_chunk(score=0.9)])
        result.metadata = {
            "rewrite": {"rewrite_status": "rewritten"},
            "rerank": {"status": "reranked"},
            "context_filter": {"status": "applied"},
        }
        decision = AbstentionDecider().decide(result)
        assert decision.details["rewrite"]["rewrite_status"] == "rewritten"
        assert decision.details["rerank"]["status"] == "reranked"
        assert decision.details["context_filter"]["status"] == "applied"
        print("[PASS] Debug 信息包含各阶段状态")

    def test_to_dict_serialisable(self):
        decision = AbstentionDecider().decide(_result([]))
        payload = decision.to_dict()
        assert payload["abstained"] is True
        assert payload["reason"] == "no_context"
        assert json.dumps(payload, ensure_ascii=False)
        print(f"[PASS] 拒答结果可序列化: {payload['reason']}")


class TestAbstentionFactory:
    def test_message_from_settings(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "ABSTENTION_MESSAGE", "自定义拒答文案")
        decider = create_abstention_decider(settings)
        decision = decider.decide(_result([]))
        assert decision.message == "自定义拒答文案"
        print("[PASS] 拒答文案可配置")

    def test_threshold_from_settings(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "ABSTENTION_SCORE_THRESHOLD", 0.4)
        monkeypatch.setattr(settings, "ABSTENTION_MIN_CONTEXT_CHUNKS", 2)
        decider = create_abstention_decider(settings)
        assert decider.score_threshold == 0.4
        assert decider.min_context_chunks == 2
        print("[PASS] 阈值来自配置")


# ---------------------------------------------------------------------------
# 2: 接入 ChatService（不调用 LLM 的拒答路径）
# ---------------------------------------------------------------------------


class _StubRetrieval:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def retrieve(self, question, knowledge_base_id, history=None, **kwargs):
        self.calls += 1
        return self.result


class _RecordingLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, stream=False, **kwargs):
        self.calls += 1
        return "这是 LLM 生成的答案 [来源1]"


def _patch_chat_service(monkeypatch, retrieval_result, decider=None):
    from app.services import chat_service as chat_service_module

    service = chat_service_module.chat_service
    llm = _RecordingLLM()
    monkeypatch.setattr(service, "_retrieval", _StubRetrieval(retrieval_result))
    monkeypatch.setattr(service, "_llm", llm)
    monkeypatch.setattr(
        service,
        "_abstention",
        decider or AbstentionDecider(),
    )
    return service, llm


class TestChatServiceAbstention:
    def test_no_answer_abstains_without_llm(self, monkeypatch):
        """无答案场景：必须拒答且**不得调用 LLM**。"""
        service, llm = _patch_chat_service(monkeypatch, _result([]))

        response = asyncio.run(service.query_knowledge("知识库里有答案吗？", 1))

        assert response.abstained is True
        assert response.abstention_reason == AbstentionReason.NO_CONTEXT
        assert response.has_knowledge is False
        assert response.sources == []
        assert llm.calls == 0, "拒答时绝不能调用 LLM"
        print(f"[PASS] 无答案拒答且未调用 LLM: {response.answer}")

    def test_low_score_abstains_without_llm(self, monkeypatch):
        """低分结果场景：阈值启用后应拒答。"""
        decider = AbstentionDecider(score_threshold=0.6)
        service, llm = _patch_chat_service(
            monkeypatch, _result([_chunk(score=0.35)]), decider
        )

        response = asyncio.run(service.query_knowledge("无关问题", 1))

        assert response.abstained is True
        assert response.abstention_reason == AbstentionReason.LOW_RETRIEVAL_SCORE
        assert llm.calls == 0
        print("[PASS] 低分结果拒答")

    def test_answering_path_calls_llm(self, monkeypatch):
        """有答案场景：正常调用 LLM 并保留引用。"""
        service, llm = _patch_chat_service(
            monkeypatch, _result([_chunk(score=0.9, rerank_score=0.8)])
        )

        response = asyncio.run(service.query_knowledge("门诊时间？", 1))

        assert response.abstained is False
        assert response.has_knowledge is True
        assert llm.calls == 1, "有依据时必须调用 LLM"
        assert len(response.sources) == 1
        assert response.citations
        print("[PASS] 有答案时正常生成")

    def test_stream_abstention_frame(self, monkeypatch):
        """流式路径：拒答应发出 no_result 控制帧（兼容前端契约）且不调用 LLM。"""
        service, llm = _patch_chat_service(monkeypatch, _result([]))

        async def collect():
            frames = []
            async for chunk in service.stream_query_knowledge("问题", 1):
                frames.append(chunk)
            return frames

        frames = asyncio.run(collect())
        assert frames, "应至少产出一帧"
        payload = json.loads(frames[0].strip())
        assert payload["type"] == "no_result"
        assert payload["abstained"] is True
        assert payload["reason"] == AbstentionReason.NO_CONTEXT
        assert payload["message"]
        assert llm.calls == 0, "流式拒答也不得调用 LLM"
        print(f"[PASS] 流式拒答帧: type={payload['type']}, reason={payload['reason']}")

    def test_stream_answering_path_calls_llm(self, monkeypatch):
        service, llm = _patch_chat_service(
            monkeypatch, _result([_chunk(score=0.9)])
        )

        async def collect():
            frames = []
            async for chunk in service.stream_query_knowledge("门诊时间？", 1):
                frames.append(chunk)
            return frames

        frames = asyncio.run(collect())
        assert llm.calls == 1
        assert any('"type": "sources"' in f for f in frames), "应发出 sources 控制帧"
        print("[PASS] 流式正常路径调用 LLM 并先发 sources")

