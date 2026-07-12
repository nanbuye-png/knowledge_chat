"""Chunking — abstraction layer for text chunking strategies.

Allows swapping between different chunking algorithms (recursive,
semantic, token‑based, etc.) without affecting DocumentService.
"""

from .base import BaseChunker
from .recursive_chunker import RecursiveChunker
from .factory import ChunkerFactory

__all__ = [
    "BaseChunker",
    "RecursiveChunker",
    "ChunkerFactory",
]