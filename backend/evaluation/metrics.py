"""检索与拒答指标 —— 纯函数、无 I/O、无网络。

设计取舍
--------
1. **相关性以「证据关键词」判定**，不以「是否来自某篇文档」判定：
   同一事实可能同时出现在多篇文档里，按文档名判定会把正确答案判成错误。
2. **nDCG 按二值相关性 + 单证据假设**计算（IDCG 取 rank=1）：
   评测集里一道题对应一组证据关键词，命中即相关。该假设写在报告里，
   避免读者误以为是多级相关性 nDCG。
3. **context precision 是代理指标**：无法为每个 chunk 标注是否相关，
   因此用 (命中证据的 chunk 数 / 返回的 chunk 数) 近似「上下文噪声率」。

所有函数只做算术，便于单元测试与离线复算（runner 记录原始 trace 后，
可以在不重新调模型的情况下重算任何指标）。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

DEFAULT_KS: tuple[int, ...] = (1, 3, 5, 10)


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------


def chunk_text(chunk: Any) -> str:
    """Return the text of a chunk, accepting dicts or plain strings."""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        return str(chunk.get("text") or "")
    return str(getattr(chunk, "text", "") or "")


def is_relevant(chunk: Any, keywords: Iterable[str]) -> bool:
    """A chunk is relevant when it contains **any** evidence keyword."""
    text = chunk_text(chunk)
    if not text:
        return False
    return any(kw and kw in text for kw in keywords)


def matched_keywords(chunk: Any, keywords: Iterable[str]) -> list[str]:
    text = chunk_text(chunk)
    return [kw for kw in keywords if kw and kw in text]


def first_relevant_rank(chunks: list[Any], keywords: Iterable[str]) -> Optional[int]:
    """1-based rank of the first relevant chunk, or ``None`` when absent."""
    for index, chunk in enumerate(chunks, start=1):
        if is_relevant(chunk, keywords):
            return index
    return None


def reciprocal_rank(chunks: list[Any], keywords: Iterable[str], k: int) -> float:
    rank = first_relevant_rank(chunks[:k], keywords)
    return 1.0 / rank if rank else 0.0


def ndcg_at_k(chunks: list[Any], keywords: Iterable[str], k: int) -> float:
    """Binary nDCG@k with the single-evidence assumption (IDCG = rank 1)."""
    rank = first_relevant_rank(chunks[:k], keywords)
    if not rank:
        return 0.0
    return 1.0 / math.log2(rank + 1)


def context_precision_at_k(chunks: list[Any], keywords: Iterable[str], k: int) -> float:
    """Proxy for context precision: relevant chunks / returned chunks (top-k)."""
    top = chunks[:k]
    if not top:
        return 0.0
    hits = sum(1 for chunk in top if is_relevant(chunk, keywords))
    return hits / len(top)


def doc_hit_at_k(chunks: list[Any], gold_docs: Iterable[str], k: int) -> bool:
    """Whether any top-k chunk comes from one of the expected documents."""
    expected = {name for name in gold_docs if name}
    if not expected:
        return False
    for chunk in chunks[:k]:
        filename = chunk.get("filename") if isinstance(chunk, dict) else None
        if filename in expected:
            return True
    return False


def format_ratio(value: float) -> str:
    return f"{value:.3f}"


# ---------------------------------------------------------------------------
# 单题 / 聚合
# ---------------------------------------------------------------------------


@dataclass
class ItemRetrievalResult:
    """One answerable item's retrieval outcome."""

    item_id: str
    category: str
    retrieved: int
    first_relevant_rank: Optional[int]
    recall: dict[str, float] = field(default_factory=dict)
    mrr_at_10: float = 0.0
    ndcg_at_5: float = 0.0
    context_precision_at_5: float = 0.0
    doc_hit_at_5: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_item_retrieval(
    item_id: str,
    category: str,
    chunks: list[Any],
    keywords: Iterable[str],
    gold_docs: Iterable[str] = (),
    ks: tuple[int, ...] = DEFAULT_KS,
) -> ItemRetrievalResult:
    """Compute every retrieval metric for a single item."""
    keywords = list(keywords)
    recall = {
        f"recall@{k}": 1.0 if first_relevant_rank(chunks[:k], keywords) else 0.0
        for k in ks
    }
    return ItemRetrievalResult(
        item_id=item_id,
        category=category,
        retrieved=len(chunks),
        first_relevant_rank=first_relevant_rank(chunks, keywords),
        recall=recall,
        mrr_at_10=reciprocal_rank(chunks, keywords, 10),
        ndcg_at_5=ndcg_at_k(chunks, keywords, 5),
        context_precision_at_5=context_precision_at_k(chunks, keywords, 5),
        doc_hit_at_5=doc_hit_at_k(chunks, gold_docs, 5),
    )


@dataclass
class RetrievalAggregate:
    """Aggregated retrieval metrics over all answerable items."""

    items: int = 0
    recall: dict[str, float] = field(default_factory=dict)
    mrr_at_10: float = 0.0
    ndcg_at_5: float = 0.0
    context_precision_at_5: float = 0.0
    doc_hit_at_5: float = 0.0
    no_retrieval_items: int = 0
    by_category: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_retrieval(results: list[ItemRetrievalResult]) -> RetrievalAggregate:
    """Average per-item retrieval metrics (macro average over items)."""
    if not results:
        return RetrievalAggregate()

    keys = sorted(results[0].recall.keys())
    recall = {key: _mean([r.recall.get(key, 0.0) for r in results]) for key in keys}

    by_category: dict[str, dict[str, float]] = {}
    for category in sorted({r.category for r in results}):
        subset = [r for r in results if r.category == category]
        by_category[category] = {
            "items": float(len(subset)),
            "recall@5": _mean([r.recall.get("recall@5", 0.0) for r in subset]),
            "mrr@10": _mean([r.mrr_at_10 for r in subset]),
            "ndcg@5": _mean([r.ndcg_at_5 for r in subset]),
        }

    return RetrievalAggregate(
        items=len(results),
        recall=recall,
        mrr_at_10=_mean([r.mrr_at_10 for r in results]),
        ndcg_at_5=_mean([r.ndcg_at_5 for r in results]),
        context_precision_at_5=_mean([r.context_precision_at_5 for r in results]),
        doc_hit_at_5=_mean([1.0 if r.doc_hit_at_5 else 0.0 for r in results]),
        no_retrieval_items=sum(1 for r in results if r.retrieved == 0),
        by_category=by_category,
    )


# ---------------------------------------------------------------------------
# 拒答与阈值标定
# ---------------------------------------------------------------------------


@dataclass
class AbstentionStats:
    """Abstention behaviour on answerable vs. unanswerable questions."""

    answerable_items: int = 0
    answerable_answered: int = 0
    answerable_abstained: int = 0
    no_answer_items: int = 0
    no_answer_abstained: int = 0
    no_answer_answered: int = 0

    @property
    def abstention_recall(self) -> float:
        """正确拒答率：无答案题目中被拒答的比例（越高越好）。"""
        return self.no_answer_abstained / self.no_answer_items if self.no_answer_items else 0.0

    @property
    def over_answer_rate(self) -> float:
        """漏拒答率：无答案题目仍被回答的比例（越低越好）。"""
        return self.no_answer_answered / self.no_answer_items if self.no_answer_items else 0.0

    @property
    def answer_rate(self) -> float:
        """可答题目被回答的比例（越高越好）。"""
        return (
            self.answerable_answered / self.answerable_items
            if self.answerable_items
            else 0.0
        )

    @property
    def false_abstention_rate(self) -> float:
        """误拒答率：可答题目被拒答的比例（越低越好）。"""
        return (
            self.answerable_abstained / self.answerable_items
            if self.answerable_items
            else 0.0
        )

    @property
    def balanced_accuracy(self) -> float:
        """(answer_rate + abstention_recall) / 2 —— 单一数字衡量拒答策略。"""
        return (self.answer_rate + self.abstention_recall) / 2

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "abstention_recall": self.abstention_recall,
                "over_answer_rate": self.over_answer_rate,
                "answer_rate": self.answer_rate,
                "false_abstention_rate": self.false_abstention_rate,
                "balanced_accuracy": self.balanced_accuracy,
            }
        )
        return payload


def abstention_stats(records: list[dict[str, Any]]) -> AbstentionStats:
    """Aggregate abstention outcomes from per-item records.

    Each record must provide ``answerable`` (bool) and ``abstained`` (bool).
    """
    stats = AbstentionStats()
    for record in records:
        if record.get("answerable"):
            stats.answerable_items += 1
            if record.get("abstained"):
                stats.answerable_abstained += 1
            else:
                stats.answerable_answered += 1
        else:
            stats.no_answer_items += 1
            if record.get("abstained"):
                stats.no_answer_abstained += 1
            else:
                stats.no_answer_answered += 1
    return stats


#: 阈值扫描的默认候选点：覆盖 0.00~0.95，步长 0.05。
#: 之所以要扫到 0.9+：hybrid 融合分的最优拒答阈值实测在 0.7 附近，
#: 旧的 (0,0.2,...,0.7) 网格会把最优点卡在边界上，看不出还能不能更好。
DEFAULT_SWEEP_THRESHOLDS: tuple[float, ...] = tuple(
    round(0.05 * index, 2) for index in range(20)
)


def threshold_sweep(
    records: list[dict[str, Any]],
    thresholds: Iterable[float] = DEFAULT_SWEEP_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Re-simulate abstention at candidate score thresholds using recorded scores.

    ``records`` items must expose ``answerable`` and ``best_score`` (the highest
    score over the **rerank output before score filtering**; ``0.0`` when empty).
    The structural term uses ``unfiltered_count`` when present (falling back to
    ``retrieved``), so "nothing was retrieved at all" still forces abstention.

    Modelled rule: ``abstain  ⇔  best_score < threshold``（等价于在
    ``RETRIEVAL_MIN_SCORE`` 之后再叠加一个更高的分数门槛），因此阈值扫描
    不依赖当次运行使用的 ``RETRIEVAL_MIN_SCORE``。
    """
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        answered = abstained = 0
        correct_abstain = over_answer = 0
        false_abstain = answered_answerable = 0
        for record in records:
            best = float(record.get("best_score") or 0.0)
            count = int(record.get("unfiltered_count", record.get("retrieved", 0)) or 0)
            should_abstain = best < threshold or count == 0
            if should_abstain:
                abstained += 1
            else:
                answered += 1
            if record.get("answerable"):
                if should_abstain:
                    false_abstain += 1
                else:
                    answered_answerable += 1
            else:
                if should_abstain:
                    correct_abstain += 1
                else:
                    over_answer += 1

        total = len(records) or 1
        answerable_total = (answered_answerable + false_abstain) or 1
        noanswer_total = (correct_abstain + over_answer) or 1
        rows.append(
            {
                "threshold": round(float(threshold), 3),
                "answered": answered,
                "abstained": abstained,
                "abstained_rate": abstained / total,
                "abstention_recall": correct_abstain / noanswer_total,
                "false_abstention_rate": false_abstain / answerable_total,
                "over_answer_rate": over_answer / noanswer_total,
                "balanced_accuracy": (
                    answered_answerable / answerable_total
                    + correct_abstain / noanswer_total
                )
                / 2,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 生成指标汇总
# ---------------------------------------------------------------------------


#: 旧版 ChatService 会把内部异常原文当成回答返回（已在 chat_service 修复）。
#: 这里兼容识别旧报告里的失败回答，避免把"系统故障"统计成"模型答错"。
LEGACY_ERROR_ANSWER_PREFIXES = (
    "抱歉，查询过程中出现错误",
    "抱歉，对话出现错误",
)


def is_generation_error(record: dict[str, Any]) -> bool:
    """本次回答是否属于**系统故障**（LLM 报错/限流），而不是模型给出的回答。

    判据优先级：

    1. ``generation_error`` 字段非空（修复后 ``ChatService`` 显式上报）；
    2. 兼容旧报告：answer 是错误文案（历史上 provider 异常被拼进了 answer）。

    这类样本必须从正确性/忠实度的分母中剔除——否则"429 限流"会被算成
    "模型答错"，指标既不可信也不可归因。
    """
    if record.get("generation_error"):
        return True
    answer = (record.get("answer") or "").lstrip()
    return answer.startswith(LEGACY_ERROR_ANSWER_PREFIXES)


@dataclass
class GenerationStats:
    """Aggregated LLM-judge outcomes (only for items that were answered)."""

    evaluated: int = 0
    judged: int = 0
    judge_errors: int = 0
    generation_errors: int = 0
    correct: int = 0
    faithful: int = 0
    empty_answers: int = 0
    cited_answers: int = 0
    #: 裁判总调用次数（含重试）与\"靠重试救回来\"的题数——限流环境下的可靠性证据
    judge_attempts: int = 0
    judge_retried: int = 0

    @property
    def correctness(self) -> float:
        return self.correct / self.judged if self.judged else 0.0

    @property
    def faithfulness(self) -> float:
        return self.faithful / self.judged if self.judged else 0.0

    @property
    def empty_answer_rate(self) -> float:
        return self.empty_answers / self.evaluated if self.evaluated else 0.0

    @property
    def generation_error_rate(self) -> float:
        return self.generation_errors / self.evaluated if self.evaluated else 0.0

    @property
    def citation_rate(self) -> float:
        return self.cited_answers / self.evaluated if self.evaluated else 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "correctness": self.correctness,
                "faithfulness": self.faithfulness,
                "empty_answer_rate": self.empty_answer_rate,
                "generation_error_rate": self.generation_error_rate,
                "citation_rate": self.citation_rate,
            }
        )
        return payload


def generation_stats(records: list[dict[str, Any]]) -> GenerationStats:
    """Aggregate judge results from per-item records that produced an answer."""
    stats = GenerationStats()
    for record in records:
        if not record.get("answered"):
            continue
        judgement = record.get("judgement")
        stats.evaluated += 1
        if is_generation_error(record):
            # 系统故障（LLM 限流/超时）：既不是回答也不是拒答，单独计数，
            # 绝不进正确性/忠实度的分母
            stats.generation_errors += 1
            continue
        if not (record.get("answer") or "").strip():
            stats.empty_answers += 1
        if record.get("has_citation"):
            stats.cited_answers += 1
        if not judgement:
            continue
        attempts = int(judgement.get("attempts", 1) or 1)
        stats.judge_attempts += attempts
        if attempts > 1:
            stats.judge_retried += 1
        if judgement.get("judge_error"):
            stats.judge_errors += 1
            continue
        stats.judged += 1
        if judgement.get("correct"):
            stats.correct += 1
        if judgement.get("faithful"):
            stats.faithful += 1
    return stats
