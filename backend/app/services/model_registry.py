"""Model Registry — read‑only abstraction for looking up LLMModel records.

Provides a single entry‑point for querying the ``llm_models`` table.
Write operations remain in :mod:`llm_model_service`.

Usage::

    registry = ModelRegistry()
    model = await registry.get_default_model(db)
    provider = LLMProviderFactory.create_from_model(model, settings)
"""

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.llm_model import LLMModel


class ModelRegistry:
    """Read‑only registry for :class:`LLMModel` records.

    Responsibilities
    ----------------
    - :meth:`get_default_model` — resolve the model to use when no
      explicit model is specified.
    - :meth:`get_model_by_name` — look up a model by its ``name``.
    - :meth:`list_models` — return all enabled models.

    All methods are **read‑only**; they never commit or modify the
    database.  Write operations belong to :mod:`llm_model_service`.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_default_model(self, db: AsyncSession) -> LLMModel | None:
        """Return the default enabled model.

        Strategy (current):
            Returns the **first** ``LLMModel`` with ``enabled=True``,
            ordered by ``id`` ascending.

        Future:
            A dedicated ``is_default`` column will make this explicit.

        Args:
            db: An active async SQLAlchemy session.

        Returns:
            The default :class:`LLMModel`, or ``None`` if no enabled
            model exists.
        """
        stmt = (
            select(LLMModel)
            .where(LLMModel.enabled == True)  # noqa: E712
            .order_by(LLMModel.id)
            .limit(1)
        )
        result = await db.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            logger.warning("No enabled LLMModel found in registry")
        return model

    async def get_model_by_name(self, db: AsyncSession, name: str) -> LLMModel | None:
        """Look up a model by its ``name`` field.

        Args:
            db: An active async SQLAlchemy session.
            name: The ``name`` column value to search for.

        Returns:
            The matching :class:`LLMModel`, or ``None`` if not found.
        """
        stmt = select(LLMModel).where(LLMModel.name == name).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_models(self, db: AsyncSession) -> list[LLMModel]:
        """Return all enabled models, ordered by ``id``.

        Args:
            db: An active async SQLAlchemy session.

        Returns:
            A list of enabled :class:`LLMModel` records.
        """
        stmt = (
            select(LLMModel)
            .where(LLMModel.enabled == True)  # noqa: E712
            .order_by(LLMModel.id)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Module‑level singleton for convenience
# ---------------------------------------------------------------------------

_model_registry = ModelRegistry()


def get_model_registry() -> ModelRegistry:
    """Return the global :class:`ModelRegistry` singleton."""
    return _model_registry