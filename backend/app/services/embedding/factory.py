"""Embedding Provider Factory — creates EmbeddingProvider instances.

Future backends (OpenAI Embeddings, Voyage, Jina, etc.) are registered
here without affecting any consumer code.
"""

from app.core.config import Settings

from .base import EmbeddingProvider
from .default_provider import DefaultEmbeddingProvider


class EmbeddingProviderFactory:
    """Factory that returns the appropriate :class:`EmbeddingProvider` implementation.

    Usage::

        provider = EmbeddingProviderFactory.create(settings)
        await provider.initialize()
        embedding = await provider.embed_query("Hello")
    """

    @staticmethod
    def create(
        settings: Settings,
        model_override: str | None = None,
    ) -> EmbeddingProvider:
        """Return the default embedding provider.

        In the future this will inspect configuration
        (e.g. ``settings.EMBEDDING_PROVIDER``) to decide which backend
        to return.

        Args:
            settings: Application settings object.
            model_override: Optional per‑KB embedding model name.
                Falls back to ``settings.EMBEDDING_MODEL`` when ``None``.

        Returns:
            A :class:`DefaultEmbeddingProvider` instance.
        """
        return DefaultEmbeddingProvider(
            model_name=model_override if model_override is not None else settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
        )
