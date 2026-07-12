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
    def create(settings: Settings) -> BaseChunker:
        """Return the default chunker (recursive paragraph‑aware).

        Args:
            settings: Application settings object.

        Returns:
            A :class:`RecursiveChunker` instance configured with
            ``CHUNK_SIZE`` and ``CHUNK_OVERLAP`` from settings.
        """
        return RecursiveChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )