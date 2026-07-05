from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger

from ..auth.deps import get_current_user
from ..models.user import User
from ..models.knowledge_base import KnowledgeBase
from ..storage.database import get_db

router = APIRouter(prefix="/api/knowledge-bases", tags=["知识库"])


# ---------- Request / Response schemas ----------

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None


class KnowledgeBaseResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ---------- Endpoints ----------

@router.get("", response_model=list[KnowledgeBaseResponse], summary="获取当前用户的所有知识库")
async def list_knowledge_bases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all knowledge bases for the authenticated user."""
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.user_id == current_user.id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    kbs = result.scalars().all()
    return [KnowledgeBaseResponse(**kb.to_dict()) for kb in kbs]


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED, summary="创建知识库")
async def create_knowledge_base(
    request: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base for the authenticated user."""
    kb = KnowledgeBase(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    logger.info(f"Knowledge base created: {kb.name} (id={kb.id}) by user {current_user.username}")
    return KnowledgeBaseResponse(**kb.to_dict())


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse, summary="更新知识库")
async def update_knowledge_base(
    kb_id: int,
    request: KnowledgeBaseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge base (rename / change description)."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    if request.name is not None:
        kb.name = request.name
    if request.description is not None:
        kb.description = request.description

    await db.commit()
    await db.refresh(kb)
    logger.info(f"Knowledge base updated: {kb.name} (id={kb.id}) by user {current_user.username}")
    return KnowledgeBaseResponse(**kb.to_dict())


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除知识库")
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a knowledge base belonging to the authenticated user."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    await db.delete(kb)
    await db.commit()
    logger.info(f"Knowledge base deleted: {kb.name} (id={kb.id}) by user {current_user.username}")