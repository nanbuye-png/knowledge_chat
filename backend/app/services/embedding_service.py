"""Embedding Service — backward‑compatible wrapper around EmbeddingProvider.

This module is kept as a compatibility shim so that existing consumers
(:mod:`main`, :mod:`health`, :mod:`document_service`,
:mod:`retrieval_pipeline`) continue to work unchanged.

All embedding logic has been migrated to :mod:`embedding.default_provider`.
"""

from loguru import logger

from ..core.config import settings
from ..core.retry import embedding_policy, retry_async
from .embedding.factory import EmbeddingProviderFactory


class EmbeddingService:
    """Compatibility layer that delegates to an :class:`EmbeddingProvider`.

    Maintains the same public API (``initialize``, ``embed_query``,
    ``embed_texts``, ``close``) while the underlying provider can be
    swapped via :class:`EmbeddingProviderFactory`.
    """

    def __init__(self):
        # 从 EMBEDDING_MODEL 中提取 provider 名称（如 "BAAI/bge-small-zh-v1.5" -> "bge"）
        model_name = settings.EMBEDDING_MODEL
        provider_name = model_name.split("/")[-1].split("-")[0] if "/" in model_name else "bge"
        self._provider = EmbeddingProviderFactory.create(
            provider_name=provider_name,
            model_name=model_name,
            embedding_dim=settings.EMBEDDING_DIM,
        )

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

        Phase 3 §5.2：远端嵌入 Provider（openai / jina / voyage）的调用会按
        ``EMBEDDING_*`` 重试策略重试瞬时错误；耗尽后抛
        :class:`~app.core.retry.RetryExhausted`（保留原始异常）。
        """
        return await retry_async(
            lambda: self._provider.embed_documents(texts),
            policy=embedding_policy(),
            operation="embed_texts",
        )

    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query text.

        Delegates to :meth:`EmbeddingProvider.embed_query`（同样带重试）。
        """
        return await retry_async(
            lambda: self._provider.embed_query(text),
            policy=embedding_policy(),
            operation="embed_query",
        )


# Singleton instance — all consumers import this
embedding_service = EmbeddingService()