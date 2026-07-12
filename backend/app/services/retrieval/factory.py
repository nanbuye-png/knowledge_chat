"""Retriever Factory — creates Retriever instances.

Future backends (Qdrant, Milvus, hybrid) are registered here without
affecting any consumer code.
"""

from .base import BaseRetriever
from .vector_retriever import VectorRetriever


class RetrieverFactory:
    """Factory that returns the appropriate :class:`BaseRetriever` implementation.

    Usage::

        retriever = RetrieverFactory.create()
        results = await retriever.retrieve(embedding, kb_id=1, top_k=5)
    """

    @staticmethod
    def create() -> BaseRetriever:
        """Return the default retriever (currently ChromaDB-backed VectorRetriever).

        In the future this will inspect configuration (``settings.VECTOR_STORE_TYPE``,
        ``settings.RETRIEVER_TYPE``, or similar) to decide which backend to return.

        Returns:
            A :class:`VectorRetriever` instance.
        """
        return VectorRetriever()