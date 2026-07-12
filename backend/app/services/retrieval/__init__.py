"""Retrieval — abstract retriever layer for vector / hybrid search.

The retriever layer decouples document search from the retrieval pipeline,
allowing different backends (Chroma, Qdrant, Milvus, hybrid) to be swapped
without changing any consumer code.
"""

from .base import BaseRetriever
from .vector_retriever import VectorRetriever
from .factory import RetrieverFactory

__all__ = [
    "BaseRetriever",
    "VectorRetriever",
    "RetrieverFactory",
]