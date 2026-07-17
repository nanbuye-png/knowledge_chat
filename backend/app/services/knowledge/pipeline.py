"""Knowledge Pipeline — unified document ingestion orchestrator.

Orchestrates document processing through existing abstraction layers:
- File parsing (parse_file)
- Chunking (ChunkerFactory) — per‑KB config
- Embedding (EmbeddingProviderFactory) — per‑KB config
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
from ..embedding.factory import EmbeddingProviderFactory
from .config import KnowledgeConfigService
from .context import KnowledgePipelineContext
from .runtime_config import KnowledgeRuntimeConfigService


class KnowledgePipeline:
    """Unified document ingestion pipeline.

    Reads per‑KB configuration via :class:`KnowledgeConfigService` and
    dynamically creates a chunker + embedding provider for each document.

    When no :class:`KnowledgeConfig` row exists for a KB, the pipeline
    falls back to the global ``settings.*`` defaults — behaviour is
    identical to KP‑5 and earlier.

    Usage::

        pipeline = KnowledgePipeline()
        ctx = KnowledgePipelineContext(
            file_path="/uploads/doc.pdf",
            document_id="abc-123",
            filename="报告.pdf",
            knowledge_base_id=1,
        )
        chunk_count = await pipeline.process_document(ctx)
    """

    def __init__(self) -> None:
        self._config_service = KnowledgeConfigService()
        self._runtime_config_service = KnowledgeRuntimeConfigService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_document(
        self,
        context: KnowledgePipelineContext,
    ) -> int:
        """Process a document through the full ingestion pipeline.

        Steps:
            1. Resolve per‑KB configuration (chunk_size, chunk_overlap,
               embedding_model) via :class:`KnowledgeRuntimeConfigService`.
            2. Parse the file into raw text.
            3. Chunk the text into overlapping segments using the resolved
               configuration.
            4. Generate embeddings for each chunk using the resolved
               embedding model.
            5. Store chunks + embeddings in the vector store.

        Args:
            context: A :class:`KnowledgePipelineContext` containing
                file_path, document_id, filename, and knowledge_base_id.

        Returns:
            The number of chunks produced.

        Raises:
            ValueError: If the document has no parseable content or chunking
                produces zero chunks.
        """
        # ── 1. Resolve per‑KB runtime configuration ────────────────────
        async with async_session() as session:
            runtime_config = await self._runtime_config_service.resolve(
                session, context.knowledge_base_id
            )

        logger.info(
            f"[KB {context.knowledge_base_id}] Runtime config: "
            f"chunk_size={runtime_config.chunk_size}, "
            f"chunk_overlap={runtime_config.chunk_overlap}, "
            f"embedding_model={runtime_config.embedding_model}"
        )

        # ── 2. Create chunker with per‑KB config ───────────────────────
        chunker = ChunkerFactory.create(
            settings,
            chunk_size=runtime_config.chunk_size,
            chunk_overlap=runtime_config.chunk_overlap,
        )

        # ── 3. Create embedding provider with per‑KB config ─────────────
        model_name = runtime_config.embedding_model or settings.EMBEDDING_MODEL
        provider_name = model_name.split("/")[-1].split("-")[0] if "/" in model_name else "bge"
        embedding_provider = EmbeddingProviderFactory.create(
            provider_name=provider_name,
            model_name=model_name,
            embedding_dim=settings.EMBEDDING_DIM,
        )
        await embedding_provider.initialize()

        try:
            # ── 4. Parse ───────────────────────────────────────────────
            logger.info(f"Parsing document: {context.filename}")
            text = parse_file(context.file_path)
            if not text.strip():
                raise ValueError("文档内容为空，无法处理")

            # ── 5. Chunk ───────────────────────────────────────────────
            logger.info(f"Chunking text: {len(text)} chars")
            chunks = chunker.chunk(text)
            if not chunks:
                raise ValueError("文档切块后内容为空")

            # ── 6. Embed ───────────────────────────────────────────────
            logger.info(f"Generating embeddings for {len(chunks)} chunks")
            embeddings = await embedding_provider.embed_documents(chunks)

            # ── 7. Look up user_id from KB ─────────────────────────────
            async with async_session() as session:
                kb_result = await session.execute(
                    select(KnowledgeBase).where(
                        KnowledgeBase.id == context.knowledge_base_id
                    )
                )
                kb = kb_result.scalar_one_or_none()
                user_id = kb.user_id if kb else None

            # ── 8. Store in vector DB ──────────────────────────────────
            logger.info(
                f"Storing {len(chunks)} chunks in vector store "
                f"(kb={context.knowledge_base_id})"
            )
            await vector_store.add_document_chunks(
                document_id=context.document_id,
                filename=context.filename,
                chunks=chunks,
                embeddings=embeddings,
                knowledge_base_id=context.knowledge_base_id,
                user_id=user_id,
            )

            logger.info(
                f"Document processed successfully: {context.filename} "
                f"({len(chunks)} chunks)"
            )
            return len(chunks)

        finally:
            # ── 9. Clean up embedding provider ─────────────────────────
            await embedding_provider.close()