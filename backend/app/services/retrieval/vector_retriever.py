"""Vector Retriever — concrete retriever backed by ChromaDB."""

from ...storage.vector_store import vector_store

from .base import BaseRetriever


class VectorRetriever(BaseRetriever):
    """Document retriever using ChromaDB as the vector store.

    Delegates to the singleton :data:`vector_store` for all search
    operations.  Does **not** perform score filtering — that is the
    responsibility of the upstream :class:`RetrievalPipeline`.
    """

    async def retrieve(
        self,
        embedding: list[float],
        knowledge_base_id: int,
        top_k: int = 5,
    ) -> list[dict]:
        """Search ChromaDB with the given query embedding.

        Args:
            embedding: Query embedding vector.
            knowledge_base_id: Restrict results to this knowledge base.
            top_k: Maximum results to return.

        Returns:
            A list of result dicts from the vector store.
        """
        return await vector_store.search(
            query_embedding=embedding,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
        )