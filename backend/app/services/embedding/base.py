"""Base Embedding Provider — abstract interface for all embedding backends.

Every concrete embedding provider (local model, OpenAI, Voyage, Jina,
custom, …) MUST inherit from :class:`EmbeddingProvider` and implement
:meth:`embed_query` and :meth:`embed_documents`.
"""
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract base class for text embedding providers.

    Implementors receive raw text and return normalized embedding vectors.
    Model loading, API keys, and retry logic are the provider's responsibility.
    """

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate an embedding for a single text.

        Canonical single‑text entry point.  Implementations may delegate
        to :meth:`embed_documents` internally.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Generate an embedding for a single query text.

        Args:
            text: The text to embed (e.g. a user question).

        Returns:
            A list of floats representing the embedding vector.
        """
        ...

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of documents.

        Args:
            texts: A list of document texts to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        ...

    async def close(self):
        """Clean up resources. Override if the provider holds state needing cleanup.

        The default implementation is a no-op.
        """
        ...
