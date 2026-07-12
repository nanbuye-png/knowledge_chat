"""Retrieval — abstract retriever layer for vector / hybrid search.

The retriever layer decouples document search from the retrieval pipeline,
allowing different backends (Chroma, Qdrant, Milvus, hybrid) to be swapped
without changing any consumer code.
"""

from .base import BaseRetriever, RetrievalProvider
from .factory import RetrieverFactory
from .models import RetrievalChunk, RetrievalResult
from .reranker import Reranker
from .vector_retriever import VectorRetriever

__all__ = [
    "BaseRetriever",
    "RetrievalProvider",
    "VectorRetriever",
    "RetrieverFactory",
    "RetrievalChunk",
    "RetrievalResult",
    "Reranker",
]
