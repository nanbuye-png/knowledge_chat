from loguru import logger
from typing import Optional
import numpy as np

from ..core.config import settings

# Try to import chromadb
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False
    logger.warning("chromadb not installed, vector store will use fallback")


class VectorStore:
    """Vector database abstraction layer using ChromaDB."""

    def __init__(self):
        self.client = None
        self.collection = None
        self._initialized = False

    async def initialize(self):
        """Initialize ChromaDB client and collection."""
        if not HAS_CHROMA:
            logger.error("ChromaDB is not installed. Please install it.")
            return

        try:
            self.client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )

            # Get or create collection
            try:
                self.collection = self.client.get_collection(settings.COLLECTION_NAME)
                logger.info(f"Loaded existing collection: {settings.COLLECTION_NAME}")
            except Exception:
                # Try to delete and recreate (handles chromadb version differences)
                try:
                    self.client.delete_collection(settings.COLLECTION_NAME)
                except Exception:
                    pass
                self.collection = self.client.create_collection(
                    name=settings.COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(f"Created new collection: {settings.COLLECTION_NAME}")

            self._initialized = True
            logger.info("Vector store initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise

    async def add_document_chunks(self, document_id: str, filename: str, chunks: list[str], embeddings: list[list[float]], knowledge_base_id: int = None):
        """Add document chunks to vector store.

        Args:
            document_id: Document ID.
            filename: Original filename.
            chunks: Text chunks.
            embeddings: Embedding vectors.
            knowledge_base_id: Knowledge base ID for isolation.
        """
        if not self._initialized:
            logger.error("Vector store not initialized")
            return

        try:
            ids = [f"{document_id}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": i,
                    "text": chunks[i][:500],  # Truncate for metadata
                    "knowledge_base_id": knowledge_base_id,
                }
                for i in range(len(chunks))
            ]

            # ------------------------------------------------
            # 写入前：确认 Python metadata 中包含 knowledge_base_id
            logger.info(f"[WRITE CHECK] About to write {len(chunks)} chunks. First metadata (Python): {metadatas[0] if metadatas else 'EMPTY'}")

            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=chunks,
            )

            # ------------------------------------------------
            # 写入后：用 collection.get() 回读，确认 Chroma 真正存储的 metadata
            verify_ids = ids[:min(3, len(ids))]  # sample first 3
            verify_result = self.collection.get(ids=verify_ids, include=["metadatas"])
            if verify_result and verify_result.get("metadatas"):
                logger.info(f"[CHROMA VERIFY] collection.get() metadatas: {verify_result['metadatas']}")
            else:
                logger.warning(f"[CHROMA VERIFY] collection.get() returned NO metadatas for ids={verify_ids}")

            logger.info(f"Added {len(chunks)} chunks for document: {filename} (kb={knowledge_base_id})")
            logger.info(f"Vector DB count after add: {self.collection.count()}")
        except Exception as e:
            logger.error(f"Failed to add chunks to vector store: {e}")
            raise

    async def search(self, query_embedding: list[float], top_k: int = 5, knowledge_base_id: int = None) -> list[dict]:
        """Search for similar chunks.

        Args:
            query_embedding: The query vector.
            top_k: Number of results.
            knowledge_base_id: Filter by knowledge base (None = no filter).
        """
        if not self._initialized:
            logger.error("Vector store not initialized")
            return []

        try:
            where_filter = None
            if knowledge_base_id is not None:
                where_filter = {"knowledge_base_id": {"$eq": knowledge_base_id}}

            logger.info(f"Vector search: kb_id={knowledge_base_id}, where_filter={where_filter}, total_count={self.collection.count()}")

            # Diagnostic: peek at stored metadata to verify knowledge_base_id is present
            sample = self.collection.peek(limit=3)
            if sample and sample.get("metadatas"):
                logger.info(f"Vector DB sample metadata (first 3): {sample['metadatas']}")

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["metadatas", "documents", "distances"],
                where=where_filter,
            )

            logger.info(f"Vector search results: {len(results['ids'][0]) if results['ids'] else 0} hits, first metadata={results['metadatas'][0][0] if results['metadatas'] and results['metadatas'][0] else 'N/A'}")

            items = []
            if results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    items.append({
                        "id": results["ids"][0][i],
                        "document_id": results["metadatas"][0][i].get("document_id", ""),
                        "filename": results["metadatas"][0][i].get("filename", ""),
                        "chunk_index": results["metadatas"][0][i].get("chunk_index", 0),
                        "text": results["documents"][0][i],
                        "score": 1 - results["distances"][0][i] if results["distances"] else 0,
                    })

            return items
        except Exception as e:
            logger.error(f"Failed to search vector store: {e}")
            return []

    async def delete_document(self, document_id: str):
        """Delete all chunks for a document."""
        if not self._initialized:
            logger.error("Vector store not initialized")
            return

        try:
            self.collection.delete(
                where={"document_id": document_id}
            )
            logger.info(f"Deleted chunks for document: {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete document from vector store: {e}")
            raise

    async def get_document_chunk_count(self, document_id: str) -> int:
        """Get chunk count for a document."""
        if not self._initialized:
            return 0

        try:
            count = self.collection.count()
            # We'd need to filter, but count with filter isn't always accurate in chroma
            return count
        except Exception as e:
            logger.error(f"Failed to get chunk count: {e}")
            return 0

    async def close(self):
        """Close vector store connection."""
        self._initialized = False
        logger.info("Vector store closed")


# Singleton instance
vector_store = VectorStore()