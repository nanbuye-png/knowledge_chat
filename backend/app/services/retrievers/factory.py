"""Retriever Factory — creates Retriever instances.

Future backends (Qdrant, Milvus, hybrid) are registered here without
affecting any consumer code.
"""

from .base import BaseRetriever
from .chroma_retriever import ChromaRetriever


class RetrieverFactory:
    """Factory that returns the appropriate :class:`BaseRetriever` implementation.

    Usage::

        retriever = RetrieverFactory.create()
        results = await retriever.retrieve(embedding, kb_id=1, top_k=5)
    """

    @staticmethod
    def create() -> BaseRetriever:
        """Return the default retriever (currently ChromaDB).

        In the future this will inspect configuration (``settings.VECTOR_STORE_TYPE``,
        ``settings.RETRIEVER_TYPE``, or similar) to decide which backend to return.

        Returns:
            A :class:`ChromaRetriever` instance.
        """
        return ChromaRetriever()