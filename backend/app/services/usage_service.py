"""LLM Usage Service — collect and persist LLM call records."""

from loguru import logger
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.llm_usage import LLMUsage


class UsageService:
    """Service for recording and querying LLM usage statistics."""

    async def record(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        conversation_id: int | None,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> LLMUsage:
        """Persist a single LLM call record.

        Args:
            db: Active async session.
            user_id: The calling user.
            conversation_id: Optional conversation context.
            provider: LLM provider name (e.g. "deepseek").
            model: Model name (e.g. "deepseek-chat").
            prompt_tokens: Input token count.
            completion_tokens: Output token count.
            total_tokens: Total token count.
            latency_ms: Call duration in milliseconds.

        Returns:
            The saved :class:`LLMUsage` row.
        """
        record = LLMUsage(
            user_id=user_id,
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        logger.debug(f"Usage recorded: user={user_id}, provider={provider}, tokens={total_tokens}")
        return record

    async def get_user_stats(self, db: AsyncSession, user_id: int) -> dict:
        """Return aggregated usage statistics for *user_id*.

        Returns:
            A dict with ``total_calls``, ``total_tokens``, ``avg_latency_ms``.
        """
        result = await db.execute(
            select(
                func.count(LLMUsage.id).label("total_calls"),
                func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.avg(LLMUsage.latency_ms), 0.0).label("avg_latency_ms"),
            ).where(LLMUsage.user_id == user_id)
        )
        row = result.one()
        return {
            "total_calls": row.total_calls,
            "total_tokens": row.total_tokens,
            "avg_latency_ms": round(row.avg_latency_ms, 2),
        }

    async def get_recent(
        self,
        db: AsyncSession,
        user_id: int,
        limit: int = 20,
    ) -> list[LLMUsage]:
        """Return the most recent usage records for *user_id*."""
        result = await db.execute(
            select(LLMUsage)
            .where(LLMUsage.user_id == user_id)
            .order_by(desc(LLMUsage.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())


usage_service = UsageService()