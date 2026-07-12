"""Embedding Provider — abstraction layer for text embedding generation.

Allows swapping between local models (BGE, SentenceTransformer),
cloud APIs (OpenAI Embeddings, Voyage, Jina), and custom backends
without changing any consumer code.
"""

from .base import EmbeddingProvider
from .default_provider import DefaultEmbeddingProvider
from .factory import EmbeddingProviderFactory

__all__ = [
    "EmbeddingProvider",
    "DefaultEmbeddingProvider",
    "EmbeddingProviderFactory",
]