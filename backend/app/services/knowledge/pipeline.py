"""Knowledge Pipeline — unified document ingestion orchestrator.

Orchestrates document processing through existing abstraction layers:
- File parsing (parse_file)
- Chunking (ChunkerFactory)
- Embedding (EmbeddingProviderFactory, via embedding_service)
- Vector storage (vector_store)

DocumentService no longer needs to know *how* a document is processed —
only that the pipeline handles it.
"""

from loguru import logger
from sqlalchemy import select

from ...core.config import settings
from ...models.knowledge_base import KnowledgeBase
from ...storage.database import async_session
from ...storage.vector_store import vector_store
from ...utils.file_parser import parse_file
from ..chunking.factory import ChunkerFactory
from ..embedding_service import embedding_service


class KnowledgePipeline:
    """Unified document ingestion pipeline.

    Usage::

        pipeline = KnowledgePipeline()
        chunk_count = await pipeline.process_document(
            file_path="/uploads/doc.pdf",
            document_id="abc-123",
            filename="报告.pdf",
            knowledge_base_id=1,
        )
    """

    def __init__(self) -> None:
        self._chunker = ChunkerFactory.create(settings)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_document(
        self,
        file_path: str,
        document_id: str,
        filename: str,
        knowledge_base_id: int,
    ) -> int:
        """Process a document through the full ingestion pipeline.

        Steps:
            1. Parse the file into raw text.
            2. Chunk the text into overlapping segments.
            3. Generate embeddings for each chunk.
            4. Store chunks + embeddings in the vector store.

        Args:
            file_path: Absolute path to the uploaded file.
            document_id: The document's unique id (used as vector store key).
            filename: Original filename (stored as metadata).
            knowledge_base_id: Target knowledge base (isolation boundary).

        Returns:
            The number of chunks produced.

        Raises:
            ValueError: If the document has no parseable content or chunking
                produces zero chunks.
        """
        # 1. Parse
        logger.info(f"Parsing document: {filename}")
        text = parse_file(file_path)
        if not text.strip():
            raise ValueError("文档内容为空，无法处理")

        # 2. Chunk
        logger.info(f"Chunking text: {len(text)} chars")
        chunks = self._chunker.chunk(text)
        if not chunks:
            raise ValueError("文档切块后内容为空")

        # 3. Embed
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        embeddings = await embedding_service.embed_texts(chunks)

        # 4. Look up user_id from KB
        async with async_session() as session:
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
            )
            kb = kb_result.scalar_one_or_none()
            user_id = kb.user_id if kb else None

        # 5. Store in vector DB
        logger.info(
            f"Storing {len(chunks)} chunks in vector store "
            f"(kb={knowledge_base_id})"
        )
        await vector_store.add_document_chunks(
            document_id=document_id,
            filename=filename,
            chunks=chunks,
            embeddings=embeddings,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
        )

        logger.info(
            f"Document processed successfully: {filename} ({len(chunks)} chunks)"
        )
        return len(chunks)