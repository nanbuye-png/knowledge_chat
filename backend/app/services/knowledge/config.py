"""KnowledgeConfigService — 管理每个知识库的 AI 参数配置。"""

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from ...models.knowledge_config import KnowledgeConfig
from ...schemas.knowledge_config import KnowledgeConfigCreate, KnowledgeConfigUpdate


class KnowledgeConfigService:
    """Read / create / update per‑KB AI configuration.

    When no config row exists for a KB, callers should fall back to
    the global ``settings.*`` defaults (see :meth:`resolve_chunk_size`,
    :meth:`resolve_retrieval_top_k`, etc.).
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_config(
        self, db: AsyncSession, knowledge_base_id: int
    ) -> KnowledgeConfig | None:
        """Return the config for *knowledge_base_id*, or ``None``.

        Args:
            db: Active async session.
            knowledge_base_id: The KB to look up.

        Returns:
            The :class:`KnowledgeConfig` row or ``None``.
        """
        stmt = select(KnowledgeConfig).where(
            KnowledgeConfig.knowledge_base_id == knowledge_base_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_default_config(
        self, db: AsyncSession, knowledge_base_id: int
    ) -> KnowledgeConfig:
        """Create a config row with every field set to ``None``.

        This means "use global defaults for everything".  Individual
        fields can be overridden later via :meth:`update_config`.

        If a config already exists for *knowledge_base_id*, it is
        returned unchanged (no duplicate rows).

        Args:
            db: Active async session.
            knowledge_base_id: KB to create config for.

        Returns:
            The new (or existing) :class:`KnowledgeConfig`.
        """
        existing = await self.get_config(db, knowledge_base_id)
        if existing is not None:
            logger.debug(
                f"KnowledgeConfig already exists for kb_id={knowledge_base_id}"
            )
            return existing

        config = KnowledgeConfig(
            knowledge_base_id=knowledge_base_id,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
        logger.info(
            f"KnowledgeConfig created (all defaults) for kb_id={knowledge_base_id}"
        )
        return config

    async def update_config(
        self,
        db: AsyncSession,
        knowledge_base_id: int,
        data: KnowledgeConfigUpdate,
    ) -> KnowledgeConfig:
        """Update (or create if missing) the config for a KB.

        Args:
            db: Active async session.
            knowledge_base_id: KB to update.
            data: Fields to update (only provided fields are changed).

        Returns:
            The updated :class:`KnowledgeConfig`.

        Raises:
            ValueError: If *knowledge_base_id* is invalid.
        """
        config = await self.get_config(db, knowledge_base_id)

        if config is None:
            config = KnowledgeConfig(knowledge_base_id=knowledge_base_id)
            db.add(config)

        update_values = data.model_dump(exclude_unset=True)
        for key, value in update_values.items():
            setattr(config, key, value)

        await db.commit()
        await db.refresh(config)
        logger.info(
            f"KnowledgeConfig updated for kb_id={knowledge_base_id}: {update_values}"
        )
        return config

    # ------------------------------------------------------------------
    # Resolver helpers (fall back to settings.* when NULL)
    # ------------------------------------------------------------------

    @staticmethod
    async def resolve_chunk_size(
        db: AsyncSession, knowledge_base_id: int
    ) -> int:
        """Return chunk_size, falling back to settings.CHUNK_SIZE."""
        stmt = select(KnowledgeConfig.chunk_size).where(
            KnowledgeConfig.knowledge_base_id == knowledge_base_id,
            KnowledgeConfig.chunk_size.isnot(None),
        )
        result = await db.execute(stmt)
        value = result.scalar_one_or_none()
        return value if value is not None else settings.CHUNK_SIZE

    @staticmethod
    async def resolve_chunk_overlap(
        db: AsyncSession, knowledge_base_id: int
    ) -> int:
        """Return chunk_overlap, falling back to settings.CHUNK_OVERLAP."""
        stmt = select(KnowledgeConfig.chunk_overlap).where(
            KnowledgeConfig.knowledge_base_id == knowledge_base_id,
            KnowledgeConfig.chunk_overlap.isnot(None),
        )
        result = await db.execute(stmt)
        value = result.scalar_one_or_none()
        return value if value is not None else settings.CHUNK_OVERLAP

    @staticmethod
    async def resolve_embedding_model(
        db: AsyncSession, knowledge_base_id: int
    ) -> str:
        """Return embedding_model, falling back to settings.EMBEDDING_MODEL."""
        stmt = select(KnowledgeConfig.embedding_model).where(
            KnowledgeConfig.knowledge_base_id == knowledge_base_id,
            KnowledgeConfig.embedding_model.isnot(None),
        )
        result = await db.execute(stmt)
        value = result.scalar_one_or_none()
        return value if value is not None else settings.EMBEDDING_MODEL

    @staticmethod
    async def resolve_retrieval_top_k(
        db: AsyncSession, knowledge_base_id: int
    ) -> int:
        """Return retrieval_top_k, falling back to 5."""
        stmt = select(KnowledgeConfig.retrieval_top_k).where(
            KnowledgeConfig.knowledge_base_id == knowledge_base_id,
            KnowledgeConfig.retrieval_top_k.isnot(None),
        )
        result = await db.execute(stmt)
        value = result.scalar_one_or_none()
        return value if value is not None else 5