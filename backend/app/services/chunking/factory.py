"""Chunker Factory — creates Chunker instances.

Future strategies (semantic chunker, token‑based, etc.) are registered
here without affecting any consumer code.
"""

from app.core.config import Settings

from .base import BaseChunker
from .recursive_chunker import RecursiveChunker


class ChunkerFactory:
    """Factory that returns the appropriate :class:`BaseChunker` implementation.

    Usage::

        chunker = ChunkerFactory.create(settings)
        chunks = chunker.chunk("长长的文档文本…")
    """

    @staticmethod
    def create(
        settings: Settings,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> BaseChunker:
        """Return the default chunker (recursive paragraph‑aware).

        Args:
            settings: Application settings object.
            chunk_size: Optional per‑KB override for chunk size.
                Falls back to ``settings.CHUNK_SIZE`` when ``None``.
            chunk_overlap: Optional per‑KB override for chunk overlap.
                Falls back to ``settings.CHUNK_OVERLAP`` when ``None``.

        Returns:
            A :class:`RecursiveChunker` instance.
        """
        return RecursiveChunker(
            chunk_size=chunk_size if chunk_size is not None else settings.CHUNK_SIZE,
            chunk_overlap=chunk_overlap if chunk_overlap is not None else settings.CHUNK_OVERLAP,
        )
