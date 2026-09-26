"""Retrieval data models — structured result containers.

Provides the canonical :class:`RetrievalResult` used by
:class:`~app.services.retrieval_pipeline.RetrievalPipeline`
and the lower‑level :class:`RetrievalChunk` for individual
document fragments.
"""

from __future__ import annotations

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
