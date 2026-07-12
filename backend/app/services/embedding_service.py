"""Embedding Service — backward‑compatible wrapper around EmbeddingProvider.

This module is kept as a compatibility shim so that existing consumers
(:mod:`main`, :mod:`health`, :mod:`document_service`,
:mod:`retrieval_pipeline`) continue to work unchanged.

All embedding logic has been migrated to :mod:`embedding.default_provider`.
"""

from loguru import logger

from ..core.config import settings
from .embedding.factory import EmbeddingProviderFactory


class EmbeddingService:
    """Compatibility layer that delegates to an :class:`EmbeddingProvider`.

    Maintains the same public API (``initialize``, ``embed_query``,
    ``embed_texts``, ``close``) while the underlying provider can be
    swapped via :class:`EmbeddingProviderFactory`.
    """

    def __init__(self):
        self._provider = EmbeddingProviderFactory.create(settings)

    # ------------------------------------------------------------------
    # Lifecycle (kept for main.py compatibility)
    # ------------------------------------------------------------------

    @property
    def _initialized(self) -> bool:
        """Exposed for health‑check compatibility."""
        return self._provider.initialized

    async def initialize(self):
        """Delegate model loading to the underlying provider."""
        await self._provider.initialize()

    async def close(self):
        """Delegate resource cleanup to the underlying provider."""
        await self._provider.close()

    # ------------------------------------------------------------------
    # Embedding API (backward‑compatible signatures)
    # ------------------------------------------------------------------

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Delegates to :meth:`EmbeddingProvider.embed_documents`.
        """
        return await self._provider.embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query text.

        Delegates to :meth:`EmbeddingProvider.embed_query`.
        """
        return await self._provider.embed_query(text)


# Singleton instance — all consumers import this
embedding_service = EmbeddingService()