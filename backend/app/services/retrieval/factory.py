"""Retriever Factory — creates Retriever instances.

检索模式由配置驱动（Phase 1 §5.2）：

* ``RETRIEVAL_MODE=hybrid`` → :class:`HybridRetriever`（向量 + BM25 融合，默认）
* ``RETRIEVAL_MODE=vector`` → :class:`VectorRetriever`（**评测 Baseline**）

未来后端（Qdrant、Milvus）在这里注册，不影响任何消费方代码。
"""

from ...core.config import settings
from .base import BaseRetriever
from .hybrid_retriever import HybridRetriever
from .vector_retriever import VectorRetriever


class RetrieverFactory:
    """Factory that returns the appropriate :class:`BaseRetriever` implementation.

    Usage::

        retriever = RetrieverFactory.create()
        results = await retriever.retrieve(embedding, kb_id=1, top_k=5, query="...")
    """

    @staticmethod
    def create(mode: str | None = None) -> BaseRetriever:
        """Create the configured retriever.

        Args:
            mode: 覆盖配置的检索模式（``hybrid`` / ``vector``）。

        Returns:
            :class:`HybridRetriever` 或 :class:`VectorRetriever`。
        """
        resolved = (mode or getattr(settings, "RETRIEVAL_MODE", "hybrid")).lower()

        if resolved == "vector":
            return VectorRetriever()

        return HybridRetriever(
            vector_weight=getattr(settings, "HYBRID_VECTOR_WEIGHT", 0.5),
            bm25_weight=getattr(settings, "HYBRID_BM25_WEIGHT", 0.5),
            recall_k=getattr(settings, "HYBRID_RECALL_K", 20),
            sparse_fallback=getattr(settings, "SPARSE_INDEX_FALLBACK", True),
        )