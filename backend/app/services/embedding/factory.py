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
    def create(settings: Settings) -> EmbeddingProvider:
        """Return the default embedding provider.

        In the future this will inspect configuration
        (e.g. ``settings.EMBEDDING_PROVIDER``) to decide which backend
        to return.

        Args:
            settings: Application settings object.

        Returns:
            A :class:`DefaultEmbeddingProvider` instance.
        """
        return DefaultEmbeddingProvider(
            model_name=settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
        )