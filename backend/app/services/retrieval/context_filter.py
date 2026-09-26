"""Context Filtering — 上下文分数阈值过滤（Phase 1 §5.4）。

```text
Reranker → Score → Threshold → Relevant Context → LLM
                        └────→ 低于阈值：不进入 LLM（并记录原因）
```

设计要点
--------
* **阈值可配置**（``CONTEXT_SCORE_THRESHOLD``），不硬编码。
* **分数来源可控**（``CONTEXT_SCORE_SOURCE``）：
  ``auto``（默认，优先 ``rerank_score``，缺失时回退召回 ``score``）/
  ``rerank`` / ``retrieval``。这样即使 Reranker 被关闭或降级，
  过滤也不会因为"分数字段缺失"而把所有 chunk 都丢掉。
* **保留 Debug 信息**：返回被过滤的 chunk 明细（id / 分数 / 文件名），
  写入 ``RetrievalResult.metadata["context_filter"]``。
* 全部被过滤时返回空上下文（上层据此走 Abstention，见 §5.6）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from loguru import logger


class ContextFilterStatus(str, Enum):
    """过滤终态。"""

    APPLIED = "applied"  # 已按阈值过滤
    DISABLED = "disabled"  # 阈值为 0 / 未启用
    SKIPPED = "skipped"  # 无候选
    ALL_FILTERED = "all_filtered"  # 全部候选都低于阈值


@dataclass
class ContextFilterOutcome:
    """过滤结果 + Debug 明细。

    Attributes:
        chunks: 通过阈值的 chunk（保持原顺序）。
        candidates_in: 进入过滤的候选数。
        kept: 保留数量。
        filtered: 被过滤的 chunk 明细（id / score / filename）。
        threshold: 本次使用的阈值。
        score_source: 本次实际使用的分数来源（rerank / retrieval）。
        status: 见 :class:`ContextFilterStatus`。
    """

    chunks: list[dict[str, Any]] = field(default_factory=list)
    candidates_in: int = 0
    kept: int = 0
    filtered: list[dict[str, Any]] = field(default_factory=list)
    threshold: float = 0.0
    score_source: str = "auto"
    status: str = ContextFilterStatus.DISABLED.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "threshold": self.threshold,
            "score_source": self.score_source,
            "candidates_in": self.candidates_in,
            "kept": self.kept,
            "filtered_count": len(self.filtered),
            "filtered": self.filtered,
        }


class ContextFilter:
    """按阈值裁剪进入 LLM 的上下文。

    Args:
        threshold: 低于该分数的 chunk 不进入 LLM；``<= 0`` 表示不启用过滤。
        score_source: ``auto`` / ``rerank`` / ``retrieval``。
    """

    def __init__(self, threshold: float = 0.0, score_source: str = "auto") -> None:
        self.threshold = float(threshold or 0.0)
        self.score_source = (score_source or "auto").lower()

    def _score_of(self, chunk: dict[str, Any]) -> Optional[float]:
        """按配置解析分数；返回 ``None`` 表示无可用分数。"""
        rerank_score = chunk.get("rerank_score")
        retrieval_score = chunk.get("score")

        if self.score_source == "rerank":
            return float(rerank_score) if rerank_score is not None else None
        if self.score_source == "retrieval":
            return float(retrieval_score) if retrieval_score is not None else None

        # auto：优先重排分，缺失时回退召回分
        if rerank_score is not None:
            return float(rerank_score)
        if retrieval_score is not None:
            return float(retrieval_score)
        return None

    def apply(self, chunks: list[dict[str, Any]]) -> ContextFilterOutcome:
        """把 *chunks* 按阈值裁剪，并返回可解释的 Debug 明细。"""
        candidates = list(chunks or [])
        if not candidates:
            return ContextFilterOutcome(
                chunks=[],
                candidates_in=0,
                kept=0,
                threshold=self.threshold,
                score_source=self.score_source,
                status=ContextFilterStatus.SKIPPED.value,
            )

        if self.threshold <= 0:
            return ContextFilterOutcome(
                chunks=candidates,
                candidates_in=len(candidates),
                kept=len(candidates),
                threshold=self.threshold,
                score_source=self.score_source,
                status=ContextFilterStatus.DISABLED.value,
            )

        kept: list[dict[str, Any]] = []
        filtered: list[dict[str, Any]] = []
        used_source = self.score_source

        for chunk in candidates:
            score = self._score_of(chunk)
            if score is None:
                # auto：缺分说明 Reranker 被关闭/降级，保守放行，避免误删全部上下文。
                # 显式指定来源：尊重调用方意图，视为不满足条件而过滤。
                if self.score_source == "auto":
                    kept.append(chunk)
                    used_source = "none"
                    continue
                filtered.append(
                    {
                        "id": chunk.get("id")
                        or f"{chunk.get('document_id')}_{chunk.get('chunk_index')}",
                        "filename": chunk.get("filename", ""),
                        "chunk_index": chunk.get("chunk_index"),
                        "score": None,
                        "reason": "missing_score",
                    }
                )
                continue
            if score >= self.threshold:
                kept.append(chunk)
            else:
                filtered.append(
                    {
                        "id": chunk.get("id")
                        or f"{chunk.get('document_id')}_{chunk.get('chunk_index')}",
                        "filename": chunk.get("filename", ""),
                        "chunk_index": chunk.get("chunk_index"),
                        "score": round(score, 6),
                        "reason": "below_threshold",
                    }
                )

        if not kept:
            status = ContextFilterStatus.ALL_FILTERED.value
        else:
            status = ContextFilterStatus.APPLIED.value

        logger.info(
            f"Context filter: threshold={self.threshold}, "
            f"source={used_source}, kept={len(kept)}, filtered={len(filtered)}"
        )

        return ContextFilterOutcome(
            chunks=kept,
            candidates_in=len(candidates),
            kept=len(kept),
            filtered=filtered,
            threshold=self.threshold,
            score_source=used_source,
            status=status,
        )
