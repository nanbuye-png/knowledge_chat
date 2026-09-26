"""Base Embedding Provider — abstract interface for all embedding backends.

Every concrete embedding provider (local model, OpenAI, Voyage, Jina,
custom, …) MUST inherit from :class:`EmbeddingProvider` and implement
:meth:`embed_query` and :meth:`embed_documents`.
"""
from abc import ABC, abstractmethod


class EmbeddingError(RuntimeError):
    """嵌入模型加载或向量生成失败。

    以**显式失败**代替"返回随机向量"的历史兜底行为：随机向量既不
    能检索到任何有意义的内容，又会静默污染向量库（审计 P0-2）。
    调用方应把它当作可恢复错误处理（记录并标记文档 FAILED / 返回错误），
    而不是让它变成"看起来成功但结果全是噪声"。
    """


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
