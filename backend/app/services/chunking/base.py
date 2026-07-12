"""Base Chunker — abstract interface for text chunking strategies.

Every concrete chunker (recursive, semantic, token‑based, …) MUST inherit
from :class:`BaseChunker` and implement :meth:`chunk`.
"""
from abc import ABC, abstractmethod


class BaseChunker(ABC):
    """Abstract base class for text chunkers.

    Implementors receive raw text and return a list of string chunks.
    """

    @abstractmethod
    def chunk(self, text: str) -> list[str]:
        """Split *text* into overlapping chunks.

        Args:
            text: Raw document text.

        Returns:
            A list of chunk strings (may be empty if the input is empty).
        """
        ...