"""LLM Usage API — query usage statistics and recent call records."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..auth.deps import get_current_user
from ..models.user import User
from ..services.usage_service import usage_service
from ..storage.database import get_db

router = APIRouter(prefix="/api/usage", tags=["用量统计"])


@router.get("/stats", summary="获取用户用量统计")
async def get_usage_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated usage stats: total calls, tokens, average latency."""
    stats = await usage_service.get_user_stats(db, current_user.id)
    return stats


@router.get("/recent", summary="获取最近调用记录")
async def get_recent_usage(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent LLM call records for the current user."""
    records = await usage_service.get_recent(db, current_user.id, limit=limit)
    return [r.to_dict() for r in records]