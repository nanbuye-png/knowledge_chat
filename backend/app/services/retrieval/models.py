"""Retrieval data models — structured result containers.

Provides the canonical :class:`RetrievalResult` used by
:class:`~app.services.retrieval_pipeline.RetrievalPipeline`
and the lower‑level :class:`RetrievalChunk` for individual
document fragments.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..citation.models import Citation


@dataclass
class RetrievalChunk:
    """A single retrieved document chunk with metadata.

    Used as the atomic unit from vector store results.  Upstream
    consumers (pipeline, prompt builder) wrap these into
    :class:`RetrievalResult`.
    """

    content: str
    document_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Container returned by :meth:`RetrievalPipeline.retrieve`.

    Attributes:
        results: Raw search results from the vector store.
        context: Formatted context string ready for prompt insertion.
        sources: List of source dicts suitable for frontend display.
        citations: Structured :class:`~app.services.citation.models.Citation` list.
        metadata: Reserved for future pipeline metadata (latency, recall, …).
        has_results: ``False`` when no relevant documents were found.
    """

    results: list[dict[str, Any]] = field(default_factory=list)
    """Raw chunks returned by the vector store."""

    context: str = ""
    """Concatenated context string (e.g. '[来源1] 文件名：…')"""

    sources: list[dict[str, Any]] = field(default_factory=list)
    """Simplified source info for the frontend (backward‑compatible)."""

    citations: list = field(default_factory=list)
    """Structured :class:`Citation` objects for reference tracking."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Reserved for future pipeline metadata (latency per step, recall count, …)."""

    original_query: str = ""
    """用户原始提问（**永不被改写覆盖**，用于引用与排查）。"""

    search_query: str = ""
    """实际用于检索的查询（默认等于 original_query，Query Rewrite 成功时不同）。"""

    rewrite_status: str = ""
    """Query Rewrite 终态：rewritten / fallback / skipped / disabled。"""

    has_results: bool = False
    """Convenience flag: ``True`` when at least one relevant chunk was found."""

    def to_dict(self) -> dict[str, Any]:
        """序列化为纯数据（Phase 3 §5.4：检索结果缓存需要可 JSON 化）。

        ``results`` / ``sources`` / ``metadata`` 本身就是 dict / list[dict]，
        ``citations`` 是 :class:`Citation` 对象，这里统一转成 dict。
        """
        return {
            "results": self.results,
            "context": self.context,
            "sources": self.sources,
            "citations": [
                c.to_dict() if hasattr(c, "to_dict") else c for c in self.citations
            ],
            "metadata": self.metadata,
            "original_query": self.original_query,
            "search_query": self.search_query,
            "rewrite_status": self.rewrite_status,
            "has_results": self.has_results,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RetrievalResult":
        """从 :meth:`to_dict` 的输出还原（缓存命中路径使用）。"""
        from ..citation.models import Citation

        # Citation.to_dict() 带 ``display`` 之类的派生字段，构造时只取真实字段
        allowed = {f.name for f in dataclasses.fields(Citation)}
        raw_citations = payload.get("citations") or []
        citations = [
            Citation(**{k: v for k, v in c.items() if k in allowed})
            for c in raw_citations
            if isinstance(c, dict)
        ]

        return cls(
            results=list(payload.get("results") or []),
            context=payload.get("context") or "",
            sources=list(payload.get("sources") or []),
            citations=citations,
            metadata=dict(payload.get("metadata") or {}),
            original_query=payload.get("original_query") or "",
            search_query=payload.get("search_query") or "",
            rewrite_status=payload.get("rewrite_status") or "",
            has_results=bool(payload.get("has_results")),
        )
