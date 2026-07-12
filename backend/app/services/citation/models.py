"""Citation data model — traceable source reference for a single chunk."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Citation:
    """A single citation linking a response to a source document chunk.

    Attributes:
        document_id: Source document unique identifier.
        filename: Original filename (for display).
        chunk_id: Chunk index within the document.
        score: Relevance / similarity score.
        metadata: Opaque metadata from the vector store.
    """

    document_id: str
    filename: str
    chunk_id: int
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)