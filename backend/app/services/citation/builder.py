"""Citation Builder — transforms raw retrieval chunks into structured citations."""

from __future__ import annotations

from typing import Any

from .models import Citation


class CitationBuilder:
    """Builds a sorted list of :class:`Citation` objects from raw retrieval results.

    Usage::

        builder = CitationBuilder()
        citations = builder.build(raw_chunks)
    """

    def build(self, chunks: list[dict[str, Any]]) -> list[Citation]:
        """Transform raw chunk dicts into a list of :class:`Citation`.

        Args:
            chunks: A list of dicts from the vector store, each containing
                at least ``document_id``, ``filename``, ``chunk_index``,
                and ``score``.

        Returns:
            A list of :class:`Citation` sorted by score descending.
        """
        citations = [
            Citation(
                document_id=r.get("document_id", ""),
                filename=r.get("filename", ""),
                chunk_id=r.get("chunk_index", 0),
                score=r.get("score", 0.0),
                metadata={k: v for k, v in r.items() if k not in ("text",)},
            )
            for r in chunks
        ]
        citations.sort(key=lambda c: c.score, reverse=True)
        return citations