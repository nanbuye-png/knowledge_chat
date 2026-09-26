"""Query Rewrite 测试（Phase 1 §5.1）。

要求（对应计划 §5.1）：
1. 保留原始 Query（永不被覆盖）
2. 生成用于 Retrieval 的 Search Query
3. 保留 Conversation Context
4. LLM Rewrite 失败必须有 fallback（超时 / 异常 / 输出非法）
5. 不允许因为 Rewrite 失败导致整个问答失败

另外验证数据结构包含 original_query / rewritten_query /
conversation_context / rewrite_status。
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.services.query.llm_rewriter import (  # noqa: E402
    LLMQueryRewriter,
    PassthroughRewriter,
)
from app.services.query.models import QueryRewriteResult, RewriteStatus  # noqa: E402


class _FakeLLM:
    """记录调用参数的可控 LLM 替身。"""

    def __init__(self, response: str = "", error: Exception | None = None, delay: float = 0.0):
        self.response = response
        self.error = error
        self.delay = delay
        self.calls: list[list[dict]] = []
        self.kwargs: list[dict] = []

    async def chat(self, messages, stream=False, **kwargs):
        self.calls.append(messages)
        self.kwargs.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.response


HISTORY = [
    {"role": "user", "content": "门诊时间是几点？"},
    {"role": "assistant", "content": "上午 08:00-12:00。"},
]


def _rewrite(rewriter, query, history=None):
    return asyncio.run(rewriter.rewrite(query, history))


# ---------------------------------------------------------------------------
# 1-3: 成功路径
# ---------------------------------------------------------------------------


class TestRewriteSuccess:
    def test_rewrites_query_and_keeps_original(self):
        llm = _FakeLLM(response="门诊挂号时间安排")
        rewriter = LLMQueryRewriter(llm=llm)

        result = _rewrite(rewriter, "它几点开始？", HISTORY)

        assert result.original_query == "它几点开始？", "原始 Query 必须保留"
        assert result.rewritten_query == "门诊挂号时间安排"
        assert result.rewrite_status == RewriteStatus.REWRITTEN.value
        assert result.has_rewrite is True
        assert result.latency_ms >= 0
        print(f"[PASS] 改写成功: {result.original_query} → {result.rewritten_query}")

    def test_conversation_context_sent_to_llm(self):
        llm = _FakeLLM(response="门诊挂号时间")
        rewriter = LLMQueryRewriter(llm=llm, max_history=4)

        result = _rewrite(rewriter, "它几点开始？", HISTORY)

        assert result.conversation_context, "必须记录参与改写的上下文"
        assert "08:00-12:00" in result.conversation_context
        prompt = llm.calls[0][-1]["content"]
        assert "门诊时间是几点" in prompt, "对话历史必须进入 Prompt"
        assert "它几点开始" in prompt, "当前问题必须进入 Prompt"
        assert llm.kwargs[0].get("temperature") == 0.0, "改写应使用确定性温度"
        print("[PASS] 对话上下文进入 Prompt")

    def test_history_truncated_to_max(self):
        llm = _FakeLLM(response="重写结果")
        rewriter = LLMQueryRewriter(llm=llm, max_history=2)

        long_history = [{"role": "user", "content": f"第{i}轮问题"} for i in range(10)]
        result = _rewrite(rewriter, "它是什么", long_history)

        assert result.conversation_context.count("\n") == 1, "最多只保留 2 条历史"
        assert "第9轮问题" in result.conversation_context
        print("[PASS] 历史裁剪正确")

    def test_output_normalisation(self):
        llm = _FakeLLM(response='重写后的查询：  "门诊 挂号  时间"\n（已重写）')
        rewriter = LLMQueryRewriter(llm=llm)

        result = _rewrite(rewriter, "它几点开始？", None)

        assert result.rewrite_status == RewriteStatus.REWRITTEN.value
        assert result.rewritten_query == "门诊 挂号 时间", result.rewritten_query
        print(f"[PASS] 输出规整: {result.rewritten_query!r}")


# ---------------------------------------------------------------------------
# 4: 失败必须 fallback
# ---------------------------------------------------------------------------


class TestRewriteFallback:
    def test_llm_exception_falls_back(self):
        llm = _FakeLLM(error=RuntimeError("upstream 500"))
        rewriter = LLMQueryRewriter(llm=llm)

        result = _rewrite(rewriter, "门诊时间是几点？", HISTORY)

        assert result.rewrite_status == RewriteStatus.FALLBACK.value
        assert result.rewritten_query == result.original_query, "必须回退为原始 Query"
        assert "RuntimeError" in result.error
        assert result.has_rewrite is False
        print(f"[PASS] LLM 异常 → fallback（{result.error[:30]}…）")

    def test_timeout_falls_back(self):
        llm = _FakeLLM(response="来不及返回", delay=5.0)
        rewriter = LLMQueryRewriter(llm=llm, timeout=0.05)

        result = _rewrite(rewriter, "门诊时间是几点？", HISTORY)

        assert result.rewrite_status == RewriteStatus.FALLBACK.value
        assert result.error == "timeout"
        assert result.rewritten_query == result.original_query
        print("[PASS] LLM 超时 → fallback")

    def test_empty_output_falls_back(self):
        llm = _FakeLLM(response="   \n  ")
        rewriter = LLMQueryRewriter(llm=llm)

        result = _rewrite(rewriter, "门诊时间是几点？", None)

        assert result.rewrite_status == RewriteStatus.FALLBACK.value
        assert result.error == "空输出"
        assert result.rewritten_query == result.original_query
        print("[PASS] 空输出 → fallback")

    def test_overlong_output_falls_back(self):
        llm = _FakeLLM(response="很长" * 200)
        rewriter = LLMQueryRewriter(llm=llm, max_chars=50)

        result = _rewrite(rewriter, "门诊时间是几点？", None)

        assert result.rewrite_status == RewriteStatus.FALLBACK.value
        assert "过长" in result.error
        print("[PASS] 超长输出 → fallback")


# ---------------------------------------------------------------------------
# 5: 跳过 / 关闭
# ---------------------------------------------------------------------------


class TestRewriteSkipAndDisable:
    def test_short_query_skipped_without_llm_call(self):
        llm = _FakeLLM(response="不应被调用")
        rewriter = LLMQueryRewriter(llm=llm, min_chars=4)

        result = _rewrite(rewriter, "在吗", None)

        assert result.rewrite_status == RewriteStatus.SKIPPED.value
        assert llm.calls == [], "过短查询不应调用 LLM"
        print("[PASS] 过短查询跳过且不调用 LLM")

    def test_empty_query_skipped(self):
        llm = _FakeLLM(response="不应被调用")
        rewriter = LLMQueryRewriter(llm=llm)

        result = _rewrite(rewriter, "   ", None)

        assert result.rewrite_status == RewriteStatus.SKIPPED.value
        assert llm.calls == []
        print("[PASS] 空查询跳过")

    def test_disabled_rewriter_passthrough(self):
        llm = _FakeLLM(response="不应被调用")
        rewriter = LLMQueryRewriter(llm=llm, enabled=False)

        result = _rewrite(rewriter, "门诊时间是几点？", HISTORY)

        assert result.rewrite_status == RewriteStatus.DISABLED.value
        assert result.rewritten_query == result.original_query
        assert llm.calls == [], "关闭时不得调用 LLM"
        print("[PASS] 关闭时透传且不调用 LLM")

    def test_passthrough_rewriter(self):
        rewriter = PassthroughRewriter()
        result = _rewrite(rewriter, "任意问题", None)
        assert isinstance(result, QueryRewriteResult)
        assert result.rewritten_query == "任意问题"
        print("[PASS] PassthroughRewriter 行为正确")


# ---------------------------------------------------------------------------
# 6: 接入检索主链路
# ---------------------------------------------------------------------------


class TestRetrievalPipelineIntegration:
    def test_pipeline_uses_rewritten_query_for_embedding(self, monkeypatch):
        """改写后的查询必须真正用于向量化（embedding 输入）。"""
        import app.services.retrieval_pipeline as pipeline_module
        from app.services.retrieval_pipeline import RetrievalPipeline

        captured = {}

        async def fake_embed(text):
            captured["text"] = text
            return [0.1, 0.2, 0.3]

        monkeypatch.setattr(
            pipeline_module.embedding_service, "embed_query", fake_embed
        )

        class _StubRewriter:
            async def rewrite(self, query, history=None):
                return QueryRewriteResult(
                    original_query=query,
                    rewritten_query="门诊挂号时间安排",
                    conversation_context="user: 门诊时间？",
                    rewrite_status=RewriteStatus.REWRITTEN.value,
                    latency_ms=12.5,
                )

        class _StubRetriever:
            async def retrieve(self, embedding, knowledge_base_id, top_k=5, query=None):
                return []

        pipeline = RetrievalPipeline()
        pipeline._rewriter = _StubRewriter()
        pipeline._retriever = _StubRetriever()

        result = asyncio.run(
            pipeline.retrieve("它几点开始？", knowledge_base_id=1, top_k=5)
        )

        assert captured["text"] == "门诊挂号时间安排", "检索必须使用改写后的查询"
        assert result.original_query == "它几点开始？"
        assert result.search_query == "门诊挂号时间安排"
        assert result.rewrite_status == RewriteStatus.REWRITTEN.value
        assert result.has_results is False
        assert result.metadata["rewrite"]["rewrite_status"] == "rewritten"
        print("[PASS] 检索链路使用改写后的 Query")

    def test_pipeline_falls_back_on_rewrite_failure(self, monkeypatch):
        """改写在链路中失败时，检索仍使用原始 Query（问答不中断）。"""
        import app.services.retrieval_pipeline as pipeline_module
        from app.services.retrieval_pipeline import RetrievalPipeline

        captured = {}

        async def fake_embed(text):
            captured["text"] = text
            return [0.4]

        monkeypatch.setattr(
            pipeline_module.embedding_service, "embed_query", fake_embed
        )

        class _FailingRewriter:
            async def rewrite(self, query, history=None):
                return QueryRewriteResult(
                    original_query=query,
                    rewritten_query=query,
                    rewrite_status=RewriteStatus.FALLBACK.value,
                    error="timeout",
                )

        class _StubRetriever:
            async def retrieve(self, embedding, knowledge_base_id, top_k=5, query=None):
                return []

        pipeline = RetrievalPipeline()
        pipeline._rewriter = _FailingRewriter()
        pipeline._retriever = _StubRetriever()

        result = asyncio.run(
            pipeline.retrieve("门诊时间是几点？", knowledge_base_id=1, top_k=5)
        )

        assert captured["text"] == "门诊时间是几点？", "失败时必须用原始 Query 检索"
        assert result.rewrite_status == RewriteStatus.FALLBACK.value
        assert result.original_query == "门诊时间是几点？"
        print("[PASS] 改写失败时回退原始 Query，链路不中断")


if __name__ == "__main__":
    print("=" * 50)
    print("Query Rewrite 测试 (Phase 1 §5.1) — 请使用 pytest 运行")
    print("=" * 50)


