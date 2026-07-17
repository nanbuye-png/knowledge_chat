"""Embedding Provider Factory 2.0 — creates embedding providers by name."""
from typing import Optional

from .base import EmbeddingProvider
from .providers import (
    BgeEmbeddingProvider,
    JinaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    VoyageEmbeddingProvider,
)


class EmbeddingProviderFactory:
    """Factory that returns the appropriate EmbeddingProvider by name."""

    _PROVIDERS = {
        "bge": BgeEmbeddingProvider,
        "jina": JinaEmbeddingProvider,
        "openai": OpenAIEmbeddingProvider,
        "voyage": VoyageEmbeddingProvider,
    }

    @staticmethod
    def create(
        provider_name: str = "bge",
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        embedding_dim: int = 768,
    ) -> EmbeddingProvider:
        """Create an embedding provider by name.

        Args:
            provider_name: One of "bge", "jina", "openai", "voyage"
            model_name: Optional model override
            api_key: Optional API key for cloud providers
            embedding_dim: Embedding dimension

        Returns:
            An EmbeddingProvider instance.

        Raises:
            ValueError: If provider_name is not supported
        """
        provider_cls = EmbeddingProviderFactory._PROVIDERS.get(provider_name.lower())
        if not provider_cls:
            raise ValueError(
                f"Unsupported embedding provider: '{provider_name}'. "
                f"Supported: {list(EmbeddingProviderFactory._PROVIDERS.keys())}"
            )

        kwargs = {"dim": embedding_dim}
        if model_name:
            kwargs["model_name" if provider_name == "bge" else "model"] = model_name
        if api_key:
            kwargs["api_key"] = api_key

        return provider_cls(**kwargs)