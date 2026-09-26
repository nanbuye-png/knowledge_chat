"""Citation Builder — transforms raw retrieval chunks into structured citations."""

from __future__ import annotations

from typing import Any

from .models import Citation

#: 系统提示词之外的引用块格式（§5.5）
SOURCES_HEADER = "Sources:"


class CitationBuilder:
    """Builds a sorted list of :class:`Citation` objects from raw retrieval results.

    Usage::

        builder = CitationBuilder()
        citations = builder.build(raw_chunks)
    """

    def build(self, chunks: list[dict[str, Any]]) -> list[Citation]:
        """Transform raw chunk dicts into a list of :class:`Citation`.

        Args:
            chunks: A list of dicts from the retrieval layer, each containing
                at least ``document_id``, ``filename``, ``chunk_index``,
                ``score``；可选的 ``page`` / ``section`` 会被透传（§5.5）。

        Returns:
            A list of :class:`Citation` sorted by score descending.
        """
        citations = [
            Citation(
                document_id=r.get("document_id", ""),
                filename=r.get("filename", ""),
                chunk_id=r.get("chunk_index", 0),
                score=r.get("score", 0.0),
                page=r.get("page"),
                section=r.get("section"),
                metadata={k: v for k, v in r.items() if k not in ("text",)},
            )
            for r in chunks
        ]
        citations.sort(key=lambda c: c.score, reverse=True)
        return citations

    @staticmethod
    def format_sources(citations: list[Citation]) -> str:
        """Render the ``Sources:`` block appended to/echoed with an answer.

        形如::

            Sources:
            - 手册.pdf · 第12页 · 门诊安排
            - 制度.docx
        """
        if not citations:
            return ""
        lines = [SOURCES_HEADER]
        for citation in citations:
            lines.append(f"- {citation.display}")
        return "\n".join(lines)