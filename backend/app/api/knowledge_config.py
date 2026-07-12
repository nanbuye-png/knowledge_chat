"""KnowledgeConfig API — per‑KnowledgeBase AI configuration CRUD."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..auth.deps import get_current_user
from ..core.config import settings
from ..models.user import User
from ..models.knowledge_base import KnowledgeBase
from ..schemas.knowledge_config import KnowledgeConfigUpdate
from ..services.knowledge.config import KnowledgeConfigService
from ..storage.database import get_db

router = APIRouter(
    prefix="/api/knowledge-bases/{knowledge_base_id}/config",
    tags=["知识库配置"],
)

config_service = KnowledgeConfigService()


# ---------------------------------------------------------------------------
# Response schema (defined here to keep the API self‑contained)
# ---------------------------------------------------------------------------

class KnowledgeConfigResponse(BaseModel):
    """Response for knowledge base AI configuration.

    When no DB row exists, all fields are resolved to global defaults
    and ``id`` / ``created_at`` / ``updated_at`` are ``None``.
    """

    knowledge_base_id: int
    chunk_size: int = Field(description="Chunk size in characters")
    chunk_overlap: int = Field(description="Chunk overlap in characters")
    embedding_provider: str | None = Field(
        None, description="Embedding provider type"
    )
    embedding_model: str = Field(description="Embedding model identifier")
    retrieval_top_k: int = Field(description="Top‑K for retrieval")
    id: int | None = Field(None, description="DB row id (None when using defaults)")
    created_at: str | None = Field(
        None, description="Creation timestamp (None when using defaults)"
    )
    updated_at: str | None = Field(
        None, description="Last update timestamp (None when using defaults)"
    )


# ---------------------------------------------------------------------------
# Helper — verify KB ownership
# ---------------------------------------------------------------------------

async def _verify_kb_ownership(
    db: AsyncSession,
    knowledge_base_id: int,
    current_user: User,
) -> None:
    """Raise 404 if the KB does not exist or does not belong to *current_user*."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )


# ---------------------------------------------------------------------------
# GET — read configuration (with fallback defaults, no DB write)
# ---------------------------------------------------------------------------

@router.get("", response_model=KnowledgeConfigResponse, summary="获取知识库AI配置")
async def get_config(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeConfigResponse:
    """Return the AI configuration for a knowledge base.

    If no explicit config row exists, every field is resolved to the
    global ``settings.*`` default — **without** creating a DB record.
    """
    await _verify_kb_ownership(db, knowledge_base_id, current_user)

    # Try to load existing config row
    config = await config_service.get_config(db, knowledge_base_id)

    if config is not None:
        # Return stored row — resolve NULLs to settings defaults
        return KnowledgeConfigResponse(
            id=config.id,
            knowledge_base_id=config.knowledge_base_id,
            chunk_size=config.chunk_size
            if config.chunk_size is not None
            else settings.CHUNK_SIZE,
            chunk_overlap=config.chunk_overlap
            if config.chunk_overlap is not None
            else settings.CHUNK_OVERLAP,
            embedding_provider=config.embedding_provider,
            embedding_model=config.embedding_model
            if config.embedding_model is not None
            else settings.EMBEDDING_MODEL,
            retrieval_top_k=config.retrieval_top_k
            if config.retrieval_top_k is not None
            else 5,
            created_at=config.created_at.isoformat() if config.created_at else None,
            updated_at=config.updated_at.isoformat() if config.updated_at else None,
        )

    # No config row → return pure defaults (no DB write)
    return KnowledgeConfigResponse(
        knowledge_base_id=knowledge_base_id,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        embedding_model=settings.EMBEDDING_MODEL,
        retrieval_top_k=5,
    )


# ---------------------------------------------------------------------------
# PUT — update (or create) configuration
# ---------------------------------------------------------------------------

@router.put("", response_model=KnowledgeConfigResponse, summary="更新知识库AI配置")
async def update_config(
    knowledge_base_id: int,
    request: KnowledgeConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeConfigResponse:
    """Update the AI configuration for a knowledge base.

    Only the fields present in the request body are changed; others are
    left untouched.  If no config row exists yet, one is created.
    """
    await _verify_kb_ownership(db, knowledge_base_id, current_user)

    config = await config_service.update_config(db, knowledge_base_id, request)

    logger.info(
        f"KnowledgeConfig updated for kb_id={knowledge_base_id} "
        f"by user {current_user.username}"
    )

    # Return with resolved defaults for NULL fields
    return KnowledgeConfigResponse(
        id=config.id,
        knowledge_base_id=config.knowledge_base_id,
        chunk_size=config.chunk_size
        if config.chunk_size is not None
        else settings.CHUNK_SIZE,
        chunk_overlap=config.chunk_overlap
        if config.chunk_overlap is not None
        else settings.CHUNK_OVERLAP,
        embedding_provider=config.embedding_provider,
        embedding_model=config.embedding_model
        if config.embedding_model is not None
        else settings.EMBEDDING_MODEL,
        retrieval_top_k=config.retrieval_top_k
        if config.retrieval_top_k is not None
        else 5,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )