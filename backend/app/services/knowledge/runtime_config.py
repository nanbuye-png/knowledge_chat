"""Knowledge Runtime Config — unified per‑KB configuration read layer.

Provides a single point of resolution for all runtime AI parameters:
chunk_size, chunk_overlap, embedding_model, retrieval_top_k.

When no :class:`KnowledgeConfig` row exists, every field falls back to
the global ``settings.*`` defaults — no DB write is performed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ...core.config import settings
from ...models.knowledge_config import KnowledgeConfig


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------


@dataclass
class KnowledgeRuntimeConfig:
    """Resolved runtime configuration for a single knowledge base.

    All fields are concrete values (no ``None``) — resolution happens
    in :meth:`KnowledgeRuntimeConfigService.resolve`.
    """

    kb_id: int
    chunk_size: int
    chunk_overlap: int
    embedding_model: str
    retrieval_top_k: int


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class KnowledgeRuntimeConfigService:
    """Unified service that resolves all per‑KB runtime config at once.

    Replaces multiple individual ``resolve_*`` calls with a single DB
    round‑trip.

    Usage::

        service = KnowledgeRuntimeConfigService()
        async with async_session() as session:
            config = await service.resolve(session, knowledge_base_id)
        # config.chunk_size, config.retrieval_top_k, …
    """

    async def resolve(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
    ) -> KnowledgeRuntimeConfig:
        """Resolve all AI runtime parameters for *knowledge_base_id*.

        Args:
            db: Active async session.
            knowledge_base_id: Target knowledge base.

        Returns:
            A :class:`KnowledgeRuntimeConfig` with every field resolved.
        """
        stmt = select(KnowledgeConfig).where(
            KnowledgeConfig.knowledge_base_id == knowledge_base_id
        )
        result = await db.execute(stmt)
        config_row: KnowledgeConfig | None = result.scalar_one_or_none()

        if config_row is None:
            # No config row — use all defaults
            runtime = KnowledgeRuntimeConfig(
                kb_id=knowledge_base_id,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
                embedding_model=settings.EMBEDDING_MODEL,
                retrieval_top_k=5,
            )
            logger.debug(
                f"[KB {knowledge_base_id}] No KnowledgeConfig row — "
                f"using global defaults"
            )
        else:
            # Resolve NULL fields to settings defaults
            runtime = KnowledgeRuntimeConfig(
                kb_id=knowledge_base_id,
                chunk_size=config_row.chunk_size
                if config_row.chunk_size is not None
                else settings.CHUNK_SIZE,
                chunk_overlap=config_row.chunk_overlap
                if config_row.chunk_overlap is not None
                else settings.CHUNK_OVERLAP,
                embedding_model=config_row.embedding_model
                if config_row.embedding_model is not None
                else settings.EMBEDDING_MODEL,
                retrieval_top_k=config_row.retrieval_top_k
                if config_row.retrieval_top_k is not None
                else 5,
            )

        logger.debug(
            f"[KB {knowledge_base_id}] Runtime config: "
            f"chunk_size={runtime.chunk_size}, "
            f"chunk_overlap={runtime.chunk_overlap}, "
            f"embedding_model={runtime.embedding_model}, "
            f"retrieval_top_k={runtime.retrieval_top_k}"
        )
        return runtime