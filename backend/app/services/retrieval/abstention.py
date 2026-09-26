"""Abstention — 知识库无足够依据时拒答，而不是让 LLM 猜测（Phase 1 §5.6）。

```text
Query → Retrieval → Relevant Context?
                     ├── YES → LLM
                     └── NO  → Abstention（固定文案，不调用 LLM）
```

判定依据（全部可配置）
----------------------
1. ``no_context``：没有任何通过过滤的上下文；
2. ``insufficient_context``：有效 chunk 数少于 ``ABSTENTION_MIN_CONTEXT_CHUNKS``；
3. ``low_retrieval_score``：最高召回分低于 ``ABSTENTION_SCORE_THRESHOLD``；
4. ``low_rerank_score``：最高重排分低于 ``ABSTENTION_RERANK_THRESHOLD``。

阈值默认 ``0.0`` 表示"不按分数拒答"，只保留结构性的"无上下文"拒答；
把阈值调到 0.2~0.3 即可启用分数维度的严格拒答（配合 Phase 2 评测调参）。

拒答时**不调用 LLM**，因此不会产生无依据的答案；``details`` 携带分数与
计数，便于 Debug 与评测归因。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


class AbstentionReason(str):
    """拒答原因常量（普通字符串，便于直接写入 JSON）。"""

    NO_CONTEXT = "no_context"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    LOW_RETRIEVAL_SCORE = "low_retrieval_score"
    LOW_RERANK_SCORE = "low_rerank_score"


DEFAULT_ABSTENTION_MESSAGE = "当前知识库中没有找到足够的信息来回答该问题。"


@dataclass
class AbstentionDecision:
    """拒答判定结果。

    Attributes:
        should_abstain: ``True`` 表示应拒答（不调用 LLM）。
        reason: :class:`AbstentionReason` 之一；未拒答时为空串。
        message: 面向用户的固定文案。
        details: 判定细节（分数/计数），用于 Debug。
    """

    should_abstain: bool = False
    reason: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "abstained": self.should_abstain,
            "reason": self.reason,
            "message": self.message,
            "details": self.details,
        }


class AbstentionDecider:
    """按配置判断"是否应拒答"。

    Args:
        enabled: ``False`` 时永不拒答（仅记录，便于对照实验）。
        message: 拒答文案。
        min_context_chunks: 有效上下文 chunk 数下限。
        score_threshold: 最高召回分下限（``<= 0`` 表示不启用）。
        rerank_threshold: 最高重排分下限（``<= 0`` 表示不启用）。
    """

    def __init__(
        self,
        enabled: bool = True,
        message: str = DEFAULT_ABSTENTION_MESSAGE,
        min_context_chunks: int = 1,
        score_threshold: float = 0.0,
        rerank_threshold: float = 0.0,
    ) -> None:
        self.enabled = enabled
        self.message = message or DEFAULT_ABSTENTION_MESSAGE
        self.min_context_chunks = max(int(min_context_chunks), 1)
        self.score_threshold = float(score_threshold or 0.0)
        self.rerank_threshold = float(rerank_threshold or 0.0)

    def decide(self, retrieval_result) -> AbstentionDecision:
        """Decide whether the retrieval result is sufficient to answer.

        Args:
            retrieval_result: :class:`~app.services.retrieval.models.RetrievalResult`
                （或任何具备 ``has_results`` / ``results`` 属性的对象）。
        """
        chunks = list(getattr(retrieval_result, "results", None) or [])
        has_results = bool(getattr(retrieval_result, "has_results", False))

        best_retrieval = max(
            (float(c.get("score", 0.0)) for c in chunks), default=0.0
        )
        rerank_scores = [
            float(c["rerank_score"]) for c in chunks if c.get("rerank_score") is not None
        ]
        best_rerank: Optional[float] = max(rerank_scores) if rerank_scores else None

        details: dict[str, Any] = {
            "context_chunks": len(chunks),
            "best_retrieval_score": round(best_retrieval, 6),
            "best_rerank_score": round(best_rerank, 6) if best_rerank is not None else None,
            "min_context_chunks": self.min_context_chunks,
            "score_threshold": self.score_threshold,
            "rerank_threshold": self.rerank_threshold,
        }

        # 阈值/开关信息始终返回；下面仍会继续判定，便于在 details 里看到全貌
        metadata = getattr(retrieval_result, "metadata", None) or {}
        for key in ("rewrite", "rerank", "context_filter"):
            if key in metadata:
                details[key] = metadata[key]

        if not self.enabled:
            details["enabled"] = False
        else:
            details["enabled"] = True

        # 安全不变量：没有可用上下文时绝不调用 LLM（不受 ABSTENTION_ENABLED 影响，
        # 否则关闭拒答后会对空上下文调用模型，必然产生无依据答案）
        if not has_results or not chunks:
            return self._abstain(AbstentionReason.NO_CONTEXT, details)

        if not self.enabled:
            return AbstentionDecision(should_abstain=False, details=details)

        if len(chunks) < self.min_context_chunks:
            return self._abstain(AbstentionReason.INSUFFICIENT_CONTEXT, details)

        if self.score_threshold > 0 and best_retrieval < self.score_threshold:
            return self._abstain(AbstentionReason.LOW_RETRIEVAL_SCORE, details)

        if (
            self.rerank_threshold > 0
            and best_rerank is not None
            and best_rerank < self.rerank_threshold
        ):
            return self._abstain(AbstentionReason.LOW_RERANK_SCORE, details)

        return AbstentionDecision(should_abstain=False, details=details)

    def _abstain(self, reason: str, details: dict[str, Any]) -> AbstentionDecision:
        logger.info(f"拒答（{reason}）: {details}")
        return AbstentionDecision(
            should_abstain=True,
            reason=reason,
            message=self.message,
            details=details,
        )


def create_abstention_decider(settings_obj=None) -> AbstentionDecider:
    """Create the configured :class:`AbstentionDecider`。"""
    from ...core.config import settings

    conf = settings_obj or settings
    return AbstentionDecider(
        enabled=getattr(conf, "ABSTENTION_ENABLED", True),
        message=getattr(conf, "ABSTENTION_MESSAGE", DEFAULT_ABSTENTION_MESSAGE),
        min_context_chunks=getattr(conf, "ABSTENTION_MIN_CONTEXT_CHUNKS", 1),
        score_threshold=getattr(conf, "ABSTENTION_SCORE_THRESHOLD", 0.0),
        rerank_threshold=getattr(conf, "ABSTENTION_RERANK_THRESHOLD", 0.0),
    )
