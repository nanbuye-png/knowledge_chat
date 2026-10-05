"""RAG 评测模块测试（Phase 2）。

覆盖三层，全部**不联网、不加载模型**：

1. **数据集真实性**：标注必须与语料一致（evidence_keywords 真的存在、
   no_answer 的 probe_terms 真的不存在、语料哈希不变），否则评测指标没有意义。
2. **指标纯函数**：Recall@K / MRR / nDCG / 上下文精确率 / 拒答统计 / 阈值扫描，
   用构造的输入断言精确数值（含边界：空结果、命中在第 1 位、命中在第 K+1 位）。
3. **LLM 裁判**：用假 Provider 覆盖正常 JSON、markdown 包裹、脏输出、
   空响应与调用异常 —— 裁判失败必须记为 judge_error，不能变成 0 分。
"""
import asyncio
import json
import os
import sys

import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from evaluation import metrics as M  # noqa: E402
from evaluation.dataset import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    load_corpus,
    load_dataset,
    validate_dataset,
)
from evaluation.judge import (  # noqa: E402
    LLMJudge,
    build_judge_prompt,
    parse_judgement,
)
from evaluation.report import render_report  # noqa: E402


def _chunk(text: str, filename: str = "doc.md", index: int = 0, score: float = 0.5):
    return {
        "text": text,
        "filename": filename,
        "chunk_index": index,
        "document_id": f"doc-{filename}",
        "score": score,
    }


# ---------------------------------------------------------------------------
# 1: 数据集与语料
# ---------------------------------------------------------------------------


class TestDatasetIntegrity:
    """评测集本身必须可信，否则后面所有数字都是假的。"""

    def test_dataset_and_corpus_load(self):
        dataset = load_dataset()
        corpus = load_corpus()
        assert dataset.items, "评测集不能为空"
        assert corpus, "语料不能为空"
        print(f"[PASS] 数据集 {len(dataset.items)} 题 / 语料 {len(corpus)} 篇")

    def test_meets_phase2_requirements(self):
        """计划要求：题目量足够、包含不可答题目、覆盖多个分类。"""
        dataset = load_dataset()
        assert len(dataset.items) >= 50, f"题量不足: {len(dataset.items)}"
        assert len(dataset.no_answer_items) >= 10, "缺少不可答（拒答）题目"
        assert len(dataset.answerable_items) >= 30, "可答题目过少"
        categories = set(dataset.category_counts()) - {"no_answer"}
        assert len(categories) >= 4, f"分类过于单一: {categories}"
        print(
            f"[PASS] 题量={len(dataset.items)} 可答={len(dataset.answerable_items)} "
            f"不可答={len(dataset.no_answer_items)} 分类={sorted(categories)}"
        )

    def test_dataset_ids_unique(self):
        ids = [item.id for item in load_dataset().items]
        assert len(ids) == len(set(ids)), "评测题 id 必须唯一"

    def test_validation_reports_no_problems(self):
        problems = validate_dataset(load_dataset(), load_corpus())
        assert problems == [], "数据集校验未通过:\n" + "\n".join(problems)

    def test_evidence_keywords_really_appear_in_corpus(self):
        """每条可答题目的每个证据关键词都必须真的出现在语料里。"""
        corpus = load_corpus()
        for item in load_dataset().answerable_items:
            for keyword in item.evidence_keywords:
                assert any(doc.contains(keyword) for doc in corpus), (
                    f"{item.id}: 证据关键词 '{keyword}' 不在任何语料中"
                )
        print("[PASS] 所有证据关键词均可在语料中定位")

    def test_no_answer_probe_terms_are_absent(self):
        """不可答题目必须真的不可答：探针词不能出现在语料里。"""
        corpus = load_corpus()
        for item in load_dataset().no_answer_items:
            for term in item.probe_terms:
                hits = [doc.name for doc in corpus if doc.contains(term)]
                assert not hits, f"{item.id}: 探针词 '{term}' 出现在 {hits}"
        print("[PASS] 所有不可答题目的探针词均不在语料中")

    def test_validation_catches_fabricated_annotation(self):
        """反向验证校验器：伪造的证据关键词必须被报出来。"""
        dataset = load_dataset()
        item_cls = type(dataset.items[0])
        broken = type(dataset)(
            version="broken",
            items=[
                item_cls(
                    id="broken-01",
                    question="虚假问题",
                    category="faq",
                    answerable=True,
                    reference_answer="不存在的答案",
                    evidence_keywords=["这段话绝对不在语料里-xyzzy"],
                )
            ],
        )
        problems = validate_dataset(broken, load_corpus())
        assert any("evidence_keyword" in p for p in problems), problems

    def test_validation_catches_answerable_no_answer_item(self):
        """反向验证：把可答事实当作 no_answer 题必须被发现。"""
        dataset = load_dataset()
        item_cls = type(dataset.items[0])
        broken = type(dataset)(
            version="broken",
            items=[
                item_cls(
                    id="broken-02",
                    question="文化宫总建筑面积是多少",
                    category="no_answer",
                    answerable=False,
                    probe_terms=["53000平方米"],
                )
            ],
        )
        problems = validate_dataset(broken, load_corpus())
        assert any("probe_term" in p for p in problems), problems

    def test_validation_catches_missing_corpus_file(self):
        from evaluation.dataset import CorpusDoc

        broken_corpus = [
            CorpusDoc(name="missing.md", path=DEFAULT_MANIFEST_PATH.parent / "nope.md", text="")
        ]
        problems = validate_dataset(load_dataset(), broken_corpus)
        assert any("语料文件不存在" in p for p in problems), problems

    def test_copied_corpus_files_match_manifest_hash(self):
        from evaluation.dataset import EVALUATION_DIR, sha256_of

        manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
        strict = [d for d in manifest["docs"] if d.get("verify_hash")]
        assert strict, "至少应有一份语料启用校验和校验"
        for entry in strict:
            # manifest 中的 path 相对 backend/evaluation/ 解析
            path = (EVALUATION_DIR / entry["path"]).resolve()
            assert path.is_file(), f"语料文件缺失: {path}"
            assert sha256_of(path) == entry["sha256"], f"语料内容已变化: {entry['name']}"
        print(f"[PASS] {len(strict)} 份语料校验和一致")

    def test_manifest_paths_exist(self):
        for doc in load_corpus():
            assert doc.exists, f"{doc.name} 路径不存在: {doc.path}"
            assert len(doc.text.strip()) > 50


# ---------------------------------------------------------------------------
# 2: 指标纯函数
# ---------------------------------------------------------------------------


KEYWORDS = ["总建筑面积大约为53000平方米"]


def _ranks_hit_at(position: int, total: int = 5):
    """构造：第 position 个 chunk（1-based）命中证据。"""
    chunks = [_chunk(f"无关内容 {i}", index=i) for i in range(1, total + 1)]
    chunks[position - 1] = _chunk("总建筑面积大约为53000平方米。", index=position)
    return chunks


class TestRetrievalMetrics:
    def test_relevance_uses_keyword_any(self):
        assert M.is_relevant(_chunk("总建筑面积大约为53000平方米"), KEYWORDS)
        assert not M.is_relevant(_chunk("没有任何相关内容"), KEYWORDS)
        assert not M.is_relevant("", KEYWORDS)

    def test_first_relevant_rank(self):
        assert M.first_relevant_rank(_ranks_hit_at(1), KEYWORDS) == 1
        assert M.first_relevant_rank(_ranks_hit_at(3), KEYWORDS) == 3
        assert M.first_relevant_rank([_chunk("无关")], KEYWORDS) is None

    def test_reciprocal_rank_respects_cutoff(self):
        chunks = _ranks_hit_at(3)
        assert M.reciprocal_rank(chunks, KEYWORDS, 3) == pytest.approx(1 / 3)
        assert M.reciprocal_rank(chunks, KEYWORDS, 2) == 0.0

    def test_ndcg_at_k(self):
        import math

        assert M.ndcg_at_k(_ranks_hit_at(1), KEYWORDS, 5) == pytest.approx(1.0)
        assert M.ndcg_at_k(_ranks_hit_at(2), KEYWORDS, 5) == pytest.approx(1 / math.log2(3))
        assert M.ndcg_at_k(_ranks_hit_at(6, total=6), KEYWORDS, 5) == 0.0

    def test_context_precision_proxy(self):
        chunks = _ranks_hit_at(1, total=2) + [_chunk("无关 A"), _chunk("无关 B")]
        assert M.context_precision_at_k(chunks, KEYWORDS, 5) == pytest.approx(1 / 4)
        assert M.context_precision_at_k([], KEYWORDS, 5) == 0.0

    def test_doc_hit_at_k(self):
        chunks = [_chunk("x", filename="a.md"), _chunk("y", filename="b.md")]
        assert M.doc_hit_at_k(chunks, ["b.md"], 5) is True
        assert M.doc_hit_at_k(chunks, ["c.md"], 5) is False
        assert M.doc_hit_at_k(chunks, [], 5) is False

    def test_evaluate_item_retrieval_fields(self):
        result = M.evaluate_item_retrieval(
            item_id="faq-12",
            category="faq",
            chunks=_ranks_hit_at(2),
            keywords=KEYWORDS,
            gold_docs=["wuxi_culture_palace_faq.txt"],
        )
        assert result.retrieved == 5
        assert result.first_relevant_rank == 2
        assert result.recall["recall@1"] == 0.0
        assert result.recall["recall@3"] == 1.0
        assert result.mrr_at_10 == pytest.approx(0.5)

    def test_aggregate_retrieval(self):
        hit_first = M.evaluate_item_retrieval("a", "faq", _ranks_hit_at(1), KEYWORDS)
        miss = M.evaluate_item_retrieval("b", "faq", [_chunk("无关")], KEYWORDS)
        aggregate = M.aggregate_retrieval([hit_first, miss])
        assert aggregate.items == 2
        assert aggregate.recall["recall@1"] == pytest.approx(0.5)
        assert aggregate.recall["recall@5"] == pytest.approx(0.5)
        assert aggregate.mrr_at_10 == pytest.approx(0.5)
        assert aggregate.by_category["faq"]["items"] == 2.0

    def test_aggregate_empty(self):
        aggregate = M.aggregate_retrieval([])
        assert aggregate.items == 0
        assert aggregate.recall == {}


class TestAbstentionMetrics:
    def _records(self):
        return [
            {"answerable": True, "abstained": False, "best_score": 0.6, "retrieved": 5},
            {"answerable": True, "abstained": True, "best_score": 0.1, "retrieved": 0},
            {"answerable": False, "abstained": True, "best_score": 0.2, "retrieved": 1},
            {"answerable": False, "abstained": False, "best_score": 0.55, "retrieved": 4},
        ]

    def test_stats(self):
        stats = M.abstention_stats(self._records())
        assert stats.answerable_items == 2
        assert stats.answerable_answered == 1
        assert stats.false_abstention_rate == pytest.approx(0.5)
        assert stats.no_answer_items == 2
        assert stats.abstention_recall == pytest.approx(0.5)
        assert stats.over_answer_rate == pytest.approx(0.5)
        assert stats.balanced_accuracy == pytest.approx(0.5)

    def test_stats_without_items(self):
        stats = M.abstention_stats([])
        assert stats.abstention_recall == 0.0
        assert stats.answer_rate == 0.0
        assert stats.balanced_accuracy == 0.0

    def test_threshold_sweep_monotonic_abstention(self):
        records = self._records()
        rows = M.threshold_sweep(records, thresholds=(0.0, 0.3, 0.6))
        # 第 2 条记录 retrieved=0（无上下文），任何阈值下都应结构性拒答
        assert [row["abstained"] for row in rows] == [1, 2, 3]
        # 阈值 0 时只剩结构性拒答，无答案题目全部漏拒答
        assert rows[0]["abstention_recall"] == pytest.approx(0.0)
        assert rows[0]["over_answer_rate"] == pytest.approx(1.0)
        # 阈值 0.6 时第 4 条（0.55）也被拒答
        assert rows[-1]["abstention_recall"] == pytest.approx(1.0)
        assert rows[-1]["false_abstention_rate"] == pytest.approx(0.5)

    def test_threshold_sweep_prefers_balanced_point(self):
        rows = M.threshold_sweep(self._records(), thresholds=(0.0, 0.3, 0.6))
        best = max(rows, key=lambda row: row["balanced_accuracy"])
        # t=0.6：可答题回答率 0.5（其中一条被误拒答），无答案题正确拒答率 1.0
        assert best["threshold"] == 0.6
        assert best["balanced_accuracy"] == pytest.approx(0.75)

    def test_threshold_sweep_counts_empty_retrieval_as_abstain(self):
        rows = M.threshold_sweep(
            [{"answerable": False, "best_score": 0.0, "retrieved": 0}], thresholds=(0.0,)
        )
        assert rows[0]["abstained"] == 1

    def test_threshold_sweep_prefers_unfiltered_count_over_retrieved(self):
        """Rerank 有结果但被分数过滤清空时，不应被当成「无上下文」拒答。"""
        rows = M.threshold_sweep(
            [
                {
                    "answerable": True,
                    "best_score": 0.8,
                    "retrieved": 0,
                    "unfiltered_count": 5,
                }
            ],
            thresholds=(0.5,),
        )
        assert rows[0]["abstained"] == 0


class TestGenerationStats:
    def test_counts_and_rates(self):
        records = [
            {
                "answered": True,
                "answer": "是 53000 平方米 [来源1]",
                "has_citation": True,
                "judgement": {"correct": True, "faithful": True},
            },
            {
                "answered": True,
                "answer": "不知道",
                "has_citation": False,
                "judgement": {"correct": False, "faithful": True},
            },
            {
                "answered": True,
                "answer": "",
                "has_citation": False,
                "judgement": {"judge_error": "parse_error"},
            },
            {"answered": False, "answer": "拒答文案", "has_citation": False},
        ]
        stats = M.generation_stats(records)
        assert stats.evaluated == 3
        assert stats.judged == 2, "judge_error 必须从分母中剔除"
        assert stats.judge_errors == 1
        assert stats.correctness == pytest.approx(0.5)
        assert stats.faithfulness == pytest.approx(1.0)
        assert stats.empty_answers == 1
        assert stats.citation_rate == pytest.approx(1 / 3)

    def test_empty_records(self):
        stats = M.generation_stats([])
        assert stats.evaluated == 0
        assert stats.correctness == 0.0


# ---------------------------------------------------------------------------
# 3: LLM 裁判
# ---------------------------------------------------------------------------


class _FakeProvider:
    """最小 LLM Provider 替身：返回固定文本或抛异常。"""

    def __init__(self, response="", error=None):
        self._model = "fake-model"
        self.response = response
        self.error = error
        self.calls = []

    async def chat(self, messages, stream=False, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if self.error is not None:
            raise self.error
        return self.response


class TestJudgeParsing:
    def test_plain_json(self):
        assert parse_judgement('{"correct": true, "faithful": false}') == {
            "correct": True,
            "faithful": False,
        }

    def test_markdown_fenced_json(self):
        raw = '```json\n{"correct": true, "faithful": true, "reason": "ok"}\n```'
        assert parse_judgement(raw)["faithful"] is True

    def test_json_with_surrounding_prose(self):
        raw = '分析如下：\n{"correct": false, "faithful": true}\n以上。'
        assert parse_judgement(raw)["correct"] is False

    def test_invalid_returns_none(self):
        assert parse_judgement("这不是 JSON") is None
        assert parse_judgement("") is None

    def test_prompt_contains_every_input(self):
        prompt = build_judge_prompt("Q?", "参考答案", "系统回答", "上下文")
        assert "Q?" in prompt and "参考答案" in prompt
        assert "系统回答" in prompt and "上下文" in prompt
        assert "correct" in prompt and "faithful" in prompt

    def test_prompt_handles_empty_reference(self):
        prompt = build_judge_prompt("Q?", "", "回答", "")
        assert "语料中没有答案" in prompt


class TestLLMJudge:
    def test_successful_judgement(self):
        provider = _FakeProvider(
            '{"correct": true, "faithful": true, "hallucination": false, "reason": "一致"}'
        )
        result = asyncio.run(
            LLMJudge(provider).judge("q1", "问题", "参考答案", "回答", "上下文")
        )
        assert result.correct is True
        assert result.faithful is True
        assert result.hallucination is False
        assert result.judge_error == ""
        assert result.reason == "一致"
        assert provider.calls[0]["kwargs"]["temperature"] == 0.0

    def test_parse_error_is_recorded_not_scored_zero(self):
        result = asyncio.run(
            LLMJudge(_FakeProvider("这不是 JSON")).judge("q2", "问题", "参考答案", "回答", "上下文")
        )
        assert result.judge_error == "parse_error"

    def test_empty_response(self):
        result = asyncio.run(
            LLMJudge(_FakeProvider("   ")).judge("q3", "问题", "参考答案", "回答", "上下文")
        )
        assert result.judge_error == "empty_judge_response"

    def test_provider_error_does_not_raise(self):
        result = asyncio.run(
            LLMJudge(_FakeProvider(error=RuntimeError("boom"))).judge(
                "q4", "问题", "参考答案", "回答", "上下文"
            )
        )
        assert result.judge_error.startswith("llm_error: ")
        assert "boom" in result.judge_error

    def test_string_booleans_are_coerced(self):
        result = asyncio.run(
            LLMJudge(_FakeProvider('{"correct": "true", "faithful": "否"}')).judge(
                "q5", "问题", "参考答案", "回答", "上下文"
            )
        )
        assert result.correct is True
        assert result.faithful is False

    def test_prompt_is_truncated_for_long_context(self):
        from evaluation.judge import MAX_CONTEXT_CHARS

        provider = _FakeProvider('{"correct": true, "faithful": true}')
        asyncio.run(
            LLMJudge(provider).judge("q6", "问题", "答案", "回答", "上" * (MAX_CONTEXT_CHARS * 3))
        )
        content = provider.calls[0]["messages"][1]["content"]
        assert len(content) < MAX_CONTEXT_CHARS * 3

    def test_create_judge_imports_app_package_correctly(self):
        """回归：`from ..core.config import ...` 会越出顶层包而崩溃。"""
        from app.core.config import Settings

        from evaluation.judge import create_judge

        conf = Settings(LLM_PROVIDER="agnes", LLM_MODEL="agnes-2.5-flash")
        judge = create_judge(conf)
        assert judge.model == "agnes-2.5-flash"
        assert judge._max_tokens == conf.EVAL_JUDGE_MAX_TOKENS
        assert judge.retry == conf.EVAL_JUDGE_RETRY
        assert judge._retry_base_delay == conf.EVAL_JUDGE_RETRY_DELAY


class _FlakyProvider:
    """前 ``fail_times`` 次抛指定异常，之后返回正常 JSON。"""

    def __init__(self, fail_times=0, error=None, response='{"correct": true, "faithful": true}'):
        self._model = "flaky-model"
        self.fail_times = fail_times
        self.error = error or RuntimeError("boom")
        self.response = response
        self.calls = 0

    async def chat(self, messages, stream=False, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return self.response


class TestJudgeRetry:
    """429 限流必须重试（实测 71 题里 20 题因 429 丢分）。"""
    def test_transient_error_classification(self):
        from evaluation.judge import is_transient_error

        assert is_transient_error(RuntimeError("Error code: 429 - rate limit exceeded"))
        assert is_transient_error(RuntimeError("You've reached the API rate limit for free users"))
        assert is_transient_error(RuntimeError("504 Gateway Timeout"))
        assert is_transient_error(RuntimeError("APIConnectionError: Connection error."))
        assert not is_transient_error(RuntimeError("401 Unauthorized: invalid api key"))
        assert not is_transient_error(ValueError("bad request body"))

    def test_rate_limit_is_retried_until_success(self):
        sleeps: list[float] = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        provider = _FlakyProvider(
            fail_times=2, error=RuntimeError("Error code: 429 - rate limit reached")
        )
        judge = LLMJudge(
            provider, retry=4, retry_base_delay=3.0, sleep=fake_sleep
        )
        result = asyncio.run(judge.judge("q7", "问题", "参考答案", "回答", "上下文"))

        assert provider.calls == 3
        assert result.judge_error == ""
        assert result.correct is True
        assert result.attempts == 3
        assert sleeps == [3.0, 6.0], "指数退避必须按 3s → 6s 递增"

    def test_backoff_is_capped(self):
        judge = LLMJudge(_FakeProvider(""), retry=6, retry_base_delay=3.0, retry_max_delay=10.0)
        assert [judge._backoff(a) for a in range(1, 6)] == [3.0, 6.0, 10.0, 10.0, 10.0]

    def test_non_transient_error_is_not_retried(self):
        provider = _FlakyProvider(fail_times=5, error=RuntimeError("401 Unauthorized"))
        judge = LLMJudge(provider, retry=4, retry_base_delay=0)
        result = asyncio.run(judge.judge("q8", "问题", "参考答案", "回答", "上下文"))

        assert provider.calls == 1, "非瞬时错误重试没有意义，只会浪费时间"
        assert result.judge_error.startswith("llm_error: ")
        assert result.attempts == 1

    def test_exhausted_retries_report_attempt_count(self):
        provider = _FlakyProvider(fail_times=99, error=RuntimeError("429 rate limit"))
        judge = LLMJudge(provider, retry=3, retry_base_delay=0, retry_max_delay=0)
        result = asyncio.run(judge.judge("q9", "问题", "参考答案", "回答", "上下文"))

        assert provider.calls == 3
        assert result.attempts == 3
        assert "429" in result.judge_error

    def test_single_attempt_when_retry_disabled(self):
        provider = _FlakyProvider(fail_times=99, error=RuntimeError("429 rate limit"))
        judge = LLMJudge(provider, retry=1)
        result = asyncio.run(judge.judge("q10", "问题", "参考答案", "回答", "上下文"))

        assert provider.calls == 1
        assert result.attempts == 1

    def test_unusable_output_is_retried(self):
        """推理型模型偶尔返回空正文：重试一次即可恢复（实测 rag-06 / na-08）。"""
        sleeps: list[float] = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        class _FirstEmpty:
            _model = "flaky-model"

            def __init__(self):
                self.calls = 0

            async def chat(self, messages, stream=False, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return ""
                return '{"correct": true, "faithful": false}'

        provider = _FirstEmpty()
        judge = LLMJudge(provider, retry=4, output_retry_delay=0.5, sleep=fake_sleep)
        result = asyncio.run(judge.judge("q11", "问题", "参考答案", "回答", "上下文"))

        assert provider.calls == 2
        assert result.judge_error == ""
        assert result.attempts == 2
        assert result.faithful is False
        assert sleeps == [0.5], "输出问题用固定短间隔，不做长退避"

    def test_non_json_output_is_retried(self):
        class _FirstBadJson:
            _model = "flaky-model"

            def __init__(self):
                self.calls = 0

            async def chat(self, messages, stream=False, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return "我认为这个回答是可信的。"
                return '{"correct": true, "faithful": true}'

        provider = _FirstBadJson()
        judge = LLMJudge(provider, retry=3, output_retry_delay=0)
        result = asyncio.run(judge.judge("q12", "问题", "参考答案", "回答", "上下文"))

        assert provider.calls == 2
        assert result.judge_error == ""
        assert result.attempts == 2

    def test_persistently_empty_output_still_counted_as_error(self):
        provider = _FakeProvider("")
        judge = LLMJudge(provider, retry=3, output_retry_delay=0)
        result = asyncio.run(judge.judge("q13", "问题", "参考答案", "回答", "上下文"))

        assert result.judge_error == "empty_judge_response"
        assert result.attempts == 3, "重试次数要如实记录"

    def test_persistently_bad_json_still_counted_as_error(self):
        provider = _FakeProvider("这不是 JSON")
        judge = LLMJudge(provider, retry=2, output_retry_delay=0)
        result = asyncio.run(judge.judge("q14", "问题", "参考答案", "回答", "上下文"))

        assert result.judge_error == "parse_error"
        assert result.attempts == 2


class TestRejudgeHelpers:
    """`--rejudge` 的选靶与上下文指纹。"""

    def test_needs_rejudge(self):
        from evaluation.runner import _needs_rejudge

        assert not _needs_rejudge({"answered": False, "judgement": {"judge_error": "x"}})
        assert _needs_rejudge({"answered": True})
        assert _needs_rejudge({"answered": True, "judgement": {}})
        assert _needs_rejudge(
            {"answered": True, "judgement": {"judge_error": "llm_error: 429"}}
        )
        assert not _needs_rejudge(
            {"answered": True, "judgement": {"judge_error": "", "correct": True}}
        )

    def test_context_signature_is_order_sensitive(self):
        from evaluation.runner import _context_signature

        a = {"filename": "d1.md", "chunk_index": 1}
        b = {"filename": "d1.md", "chunk_index": 2}
        assert _context_signature([a, b]) == [["d1.md", 1], ["d1.md", 2]]
        assert _context_signature([a, b]) != _context_signature([b, a])

    def test_context_signature_ignores_document_id(self):
        """重新入库会换 document_id，指纹不能因此误报不一致。"""
        from evaluation.runner import _context_signature

        before = [{"filename": "a.md", "chunk_index": 0, "document_id": "uuid-1"}]
        after = [{"filename": "a.md", "chunk_index": 0, "document_id": "uuid-2"}]
        assert _context_signature(before) == _context_signature(after)

    def test_context_text_joins_chunk_bodies(self):
        from evaluation.runner import _context_text

        assert _context_text([{"text": "甲"}, {"text": "乙"}]) == "甲\n\n乙"
        assert _context_text([{"text": None}]) == ""

    def test_generation_stats_counts_attempts(self):
        stats = M.generation_stats(
            [
                {
                    "answered": True,
                    "answer": "a",
                    "judgement": {"correct": True, "faithful": True, "attempts": 3},
                },
                {
                    "answered": True,
                    "answer": "b",
                    "judgement": {"judge_error": "llm_error: 429", "attempts": 4},
                },
                {"answered": True, "answer": "c", "judgement": {"correct": False}},
            ]
        )
        assert stats.judge_attempts == 8
        assert stats.judge_retried == 2
        assert stats.judged == 2
        assert stats.judge_errors == 1


class TestGenerationErrors:
    """系统故障（LLM 报错）绝不能算成"模型答错"。

    实测教训：免费额度 429 时，旧版 ChatService 把 provider 异常原文当回答返回，
    12 条这样的"回答"被裁判判为不忠实，正确性/忠实度因此被污染。
    """

    def test_explicit_generation_error_field(self):
        assert M.is_generation_error(
            {"answer": "抱歉，服务暂时不可用，请稍后重试。", "generation_error": "APIError: 429"}
        )

    def test_legacy_error_answer_text_is_detected(self):
        assert M.is_generation_error(
            {"answer": "抱歉，查询过程中出现错误：Error code: 429 - rate limit"}
        )
        assert M.is_generation_error({"answer": "抱歉，对话出现错误：boom"})

    def test_real_answer_is_not_flagged(self):
        assert not M.is_generation_error({"answer": "总建筑面积约 53000 平方米。"})
        assert not M.is_generation_error({"answer": "抱歉，知识库中没有足够信息。"})

    def test_generation_errors_are_excluded_from_denominator(self):
        stats = M.generation_stats(
            [
                {"answered": True, "answer": "真实回答", "judgement": {"correct": True}},
                {
                    "answered": True,
                    "answer": "抱歉，查询过程中出现错误：429",
                    "judgement": {"correct": False, "faithful": False},
                    "generation_error": "APIError: 429",
                },
                {"answered": True, "answer": "真实回答2", "judgement": {"correct": False}},
            ]
        )
        assert stats.evaluated == 3
        assert stats.generation_errors == 1
        assert stats.judged == 2, "系统故障不进分母"
        assert stats.correct == 1
        assert stats.correctness == pytest.approx(0.5)
        assert stats.generation_error_rate == pytest.approx(1 / 3)

    def test_recompute_derived_refreshes_all_downstream_metrics(self):
        """补判/重生成后，派生指标必须整体刷新，避免"新答案 + 旧指标"。"""
        from evaluation import report as R
        from evaluation.runner import _recompute_derived

        payload = {
            "items": [
                {
                    "id": "q1",
                    "answerable": True,
                    "answered": True,
                    "abstained": False,
                    "abstained_decision": False,
                    "abstention_matches": True,
                    "best_score": 0.9,
                    "unfiltered_count": 5,
                    "retrieved": 5,
                    "answer": "回答",
                    "has_citation": True,
                    "citations": {"has_reference_marker": True},
                    "judgement": {"correct": True, "faithful": True},
                },
                {
                    "id": "q2",
                    "answerable": False,
                    "answered": True,
                    "abstained": False,
                    "abstained_decision": True,
                    "abstention_matches": False,
                    "best_score": 0.8,
                    "unfiltered_count": 5,
                    "retrieved": 5,
                    "answer": "抱歉，查询过程中出现错误：429",
                    "generation_error": "APIError: 429",
                    "judgement": {"correct": False},
                },
            ],
            "run": {"pipeline_config": {}},
        }
        payload["generation"] = {"evaluated": 99}  # 陈旧值
        _recompute_derived(payload)
        assert payload["generation"]["evaluated"] == 2
        assert payload["generation"]["generation_errors"] == 1
        assert payload["generation"]["judged"] == 1
        assert payload["citations"]["answered_items"] == 2
        assert payload["abstention"]["no_answer_items"] == 1
        assert payload["consistency"]["abstention_mismatches"] == ["q2"]
        assert len(payload["threshold_sweep"]) == 20
        assert "系统故障" in R._generation_table(payload)


# ---------------------------------------------------------------------------
# 4: 报告渲染
# ---------------------------------------------------------------------------


def _payload(use_llm: bool = True) -> dict:
    """Synthetic run payload (same shape as the runner writes)."""
    item = {
        "index": 1,
        "id": "faq-12",
        "category": "faq",
        "answerable": True,
        "question": "总建筑面积？",
        "reference_answer": "53000 平方米",
        "retrieved": 2,
        "has_results": True,
        "best_score": 0.62,
        "best_rerank": 0.9,
        "rewrite_status": "disabled",
        "search_query": "总建筑面积？",
        "abstained_decision": False,
        "abstention_reason": "",
        "retrieval_ms": 12.0,
        "chunks": [],
        "retrieval": {
            "item_id": "faq-12",
            "category": "faq",
            "retrieved": 2,
            "first_relevant_rank": 1,
            "recall": {
                "recall@1": 1.0,
                "recall@3": 1.0,
                "recall@5": 1.0,
                "recall@10": 1.0,
            },
            "mrr_at_10": 1.0,
            "ndcg_at_5": 1.0,
            "context_precision_at_5": 0.5,
            "doc_hit_at_5": True,
        },
    }
    if use_llm:
        item.update(
            {
                "answer": "53000 平方米 [来源1]",
                "abstained": False,
                "empty_answer": False,
                "has_citation": True,
                "citations": {
                    "count": 2,
                    "located": 1,
                    "is_consistent": True,
                    "invalid_reference_indices": [],
                    "has_reference_marker": True,
                },
                "judgement": {"correct": True, "faithful": True, "judge_error": ""},
            }
        )

    return {
        "schema_version": 1,
        "run": {
            "started_at": "2026-09-29T00:00:00+00:00",
            "finished_at": "2026-09-29T00:01:00+00:00",
            "duration_seconds": 60.0,
            "config": {"mode": "hybrid"},
            "workspace": "C:/tmp/x",
            "pipeline_config": {
                "RETRIEVAL_MODE": "hybrid",
                "HYBRID_VECTOR_WEIGHT": 0.5,
                "HYBRID_BM25_WEIGHT": 0.5,
                "HYBRID_RECALL_K": 20,
                "RERANKER_ENABLED": True,
                "RERANKER_TYPE": "lexical",
                "RERANKER_TOP_K": 5,
                "CONTEXT_SCORE_THRESHOLD": 0.0,
                "CONTEXT_SCORE_SOURCE": "auto",
                "ABSTENTION_MIN_CONTEXT_CHUNKS": 1,
                "ABSTENTION_SCORE_THRESHOLD": 0.0,
                "ABSTENTION_RERANK_THRESHOLD": 0.0,
                "QUERY_REWRITE_ENABLED": False,
                "CHUNK_SIZE": 2000,
                "CHUNK_OVERLAP": 200,
                "EMBEDDING_MODEL": "BAAI/bge-small-zh-v1.5",
                "EMBEDDING_DIM": 512,
                "LLM_PROVIDER": "agnes",
                "LLM_MODEL": "agnes-2.5-flash",
            },
            "judge_model": "agnes-2.5-flash" if use_llm else None,
            "dataset": {
                "path": "rag_eval_v1.json",
                "version": "1.0",
                "items": 1,
                "answerable": 1,
                "no_answer": 0,
                "categories": {"faq": 1},
            },
            "corpus": {
                "documents": 1,
                "chars": 100,
                "roles": {"primary": 1},
                "docs": [],
            },
            "ingestion": [
                {
                    "document_id": "d1",
                    "filename": "faq.txt",
                    "role": "primary",
                    "chars": 100,
                    "chunks": 2,
                    "status": "completed",
                    "error_message": None,
                    "seconds": 1.0,
                }
            ],
            "llm_calls_expected": 2,
        },
        "retrieval": {
            "items": 1,
            "recall": {
                "recall@1": 1.0,
                "recall@3": 1.0,
                "recall@5": 1.0,
                "recall@10": 1.0,
            },
            "mrr_at_10": 1.0,
            "ndcg_at_5": 1.0,
            "context_precision_at_5": 0.5,
            "doc_hit_at_5": 1.0,
            "no_retrieval_items": 0,
            "by_category": {
                "faq": {"items": 1.0, "recall@5": 1.0, "mrr@10": 1.0, "ndcg@5": 1.0}
            },
        },
        "retrieval_pool": {
            "items": 1,
            "recall": {
                "recall@1": 1.0,
                "recall@3": 1.0,
                "recall@5": 1.0,
                "recall@10": 1.0,
            },
            "mrr_at_10": 1.0,
            "ndcg_at_5": 1.0,
            "context_precision_at_5": 0.25,
            "doc_hit_at_5": 1.0,
            "no_retrieval_items": 0,
            "by_category": {},
        },
        "retrieval_production": {
            "items": 1,
            "recall": {
                "recall@1": 0.0,
                "recall@3": 0.0,
                "recall@5": 0.0,
                "recall@10": 0.0,
            },
            "mrr_at_10": 0.0,
            "ndcg_at_5": 0.0,
            "context_precision_at_5": 1.0,
            "doc_hit_at_5": 0.0,
            "no_retrieval_items": 1,
            "by_category": {},
        },
        "context_sizes": {
            "pool_mean": 20.0,
            "unfiltered_mean": 5.0,
            "production_mean": 1.0,
            "items_filtered_below_top5": 1,
        },
        "abstention": {
            "answerable_items": 1,
            "answerable_answered": 1,
            "answerable_abstained": 0,
            "no_answer_items": 1,
            "no_answer_abstained": 1,
            "no_answer_answered": 0,
            "abstention_recall": 1.0,
            "over_answer_rate": 0.0,
            "answer_rate": 1.0,
            "false_abstention_rate": 0.0,
            "balanced_accuracy": 1.0,
        },
        "generation": M.generation_stats(
            [
                {
                    "answered": True,
                    "answer": "53000 平方米",
                    "has_citation": True,
                    "judgement": {"correct": True, "faithful": True},
                }
            ]
            if use_llm
            else []
        ).to_dict(),
        "citations": {
            "answered_items": 1,
            "items_with_citations": 1,
            "citation_rate": 1.0,
            "consistent_items": 1,
            "consistency_rate": 1.0,
            "items_with_fabricated_reference": 0,
            "fabricated_reference_rate": 0.0,
            "total_citations": 2,
            "located_citations": 1,
            "locator_coverage": 0.5,
            "reference_marker_items": 1,
        },
        "consistency": {
            "llm_items": 1,
            "abstention_matches": 1,
            "abstention_mismatches": [],
        },
        "threshold_sweep": [
            {
                "threshold": 0.0,
                "answered": 1,
                "abstained": 1,
                "abstained_rate": 0.5,
                "abstention_recall": 1.0,
                "false_abstention_rate": 0.0,
                "over_answer_rate": 0.0,
                "balanced_accuracy": 1.0,
            }
        ],
        "problems": [],
        "items": [item],
    }


class TestReportRendering:
    def test_renders_all_sections(self):
        markdown = render_report(_payload())
        for heading in (
            "## 1. 结论速览",
            "## 4. 检索质量",
            "## 5. 拒答与阈值标定",
            "## 6. 生成质量",
            "## 7. 引用质量",
            "## 8. 失败案例",
            "## 9. 方法论与局限",
            "## 10. 如何复现",
        ):
            assert heading in markdown, f"缺少章节: {heading}"

    def test_values_come_from_payload(self):
        markdown = render_report(_payload())
        assert "100.0%" in markdown  # recall@5 = 1.0
        assert "0.500" in markdown  # context precision = 0.5
        assert "agnes-2.5-flash" in markdown
        assert "faq.txt" in markdown

    def test_context_size_comparison_row(self):
        markdown = render_report(_payload())
        assert "① 召回池（top_k=20，无过滤）" in markdown
        assert "② Rerank 后（top_k=5，无分数过滤）" in markdown
        assert "③ 分数过滤后（生产配置，进入 LLM）" in markdown
        assert "平均上下文条数：召回池 20.0 → Rerank 后 5.0 → 分数过滤后 1.0" in markdown

    def test_no_llm_payload_marks_generation_skipped(self):
        assert "未评测生成质量" in render_report(_payload(use_llm=False))

    def test_baseline_delta_column(self):
        baseline = _payload()
        baseline["retrieval"]["recall"]["recall@5"] = 0.5
        markdown = render_report(_payload(), baseline=baseline)
        assert "Vector（基线）" in markdown
        assert "+50.0pp" in markdown

    def test_failure_cases_are_listed(self):
        payload = _payload()
        payload["items"][0]["retrieval"]["first_relevant_rank"] = None
        payload["items"][0]["empty_answer"] = True
        markdown = render_report(payload)
        assert "检索未命中证据" in markdown
        assert "空回答" in markdown
        assert "`faq-12`" in markdown
