"""Citation data model — traceable source reference for a single chunk."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Citation:
    """A single citation linking a response to a source document chunk.

    Attributes:
        document_id: Source document unique identifier.
        filename: Original filename (for display) —— 即 ``source``。
        chunk_id: Chunk index within the document.
        score: Relevance / similarity score.
        page: 页码（PDF 等有页号标记的格式；无法定位时为 ``None``）。
        section: 所属章节/标题（启发式定位；无法定位时为 ``None``）。
        metadata: Opaque metadata from the vector store.
    """

    document_id: str
    filename: str
    chunk_id: int
    score: float
    page: Optional[int] = None
    section: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def source(self) -> str:
        """人类可读的来源名称（默认取文件名）。"""
        return self.filename or self.document_id

    @property
    def display(self) -> str:
        """``文件名 · 第N页 · 章节`` —— 引用展示用。"""
        parts = [self.source]
        if self.page is not None:
            parts.append(f"第{self.page}页")
        if self.section:
            parts.append(self.section)
        return " · ".join(parts)

    @property
    def locator(self) -> dict[str, Any]:
        """结构化的可追溯定位信息。"""
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "source": self.source,
            "page": self.page,
            "section": self.section,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "chunk_id": self.chunk_id,
            "score": self.score,
            "page": self.page,
            "section": self.section,
            "display": self.display,
        }
