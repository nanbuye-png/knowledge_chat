from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete
from loguru import logger

from ..auth.deps import get_current_user
from ..models.user import User
from ..models.knowledge_base import KnowledgeBase
from ..models.document import Document
from ..models.conversation import Conversation
from ..storage.database import get_db
from ..storage.vector_store import vector_store
from ..services.audit_service import create_audit_log

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
    document_count: int = 0
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
        select(KnowledgeBase, func.count(Document.id).label('doc_count'))
        .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
        .where(KnowledgeBase.user_id == current_user.id)
        .group_by(KnowledgeBase.id)
        .order_by(KnowledgeBase.updated_at.desc())
    )
    rows = result.all()
    return [
        KnowledgeBaseResponse(
            id=kb.id,
            user_id=kb.user_id,
            name=kb.name,
            description=kb.description,
            document_count=doc_count,
            created_at=kb.created_at.isoformat() if kb.created_at else None,
            updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
        )
        for kb, doc_count in rows
    ]


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
    await create_audit_log(
        db=db, operator_id=current_user.id, action="KNOWLEDGE_CREATE",
        target_type="knowledge_base", target_id=kb.id,
        detail={"name": kb.name}, status="SUCCESS",
    )
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


@router.patch("/{kb_id}", response_model=KnowledgeBaseResponse, summary="部分更新知识库")
async def partial_update_knowledge_base(
    kb_id: int,
    request: KnowledgeBaseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partially update a knowledge base (PATCH alias for PUT)."""
    return await update_knowledge_base(kb_id, request, current_user, db)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除知识库")
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a knowledge base and all associated resources (documents, conversations, messages)."""
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

    # 1. Delete all ChromaDB vectors for this knowledge base (single call)
    try:
        await vector_store.delete_knowledge_base(kb_id)
    except Exception as e:
        logger.warning(f"Failed to delete vectors for knowledge base {kb_id}: {e}")

    # 2. Delete all conversations under this KB (cascades to messages via DB FK)
    await db.execute(sa_delete(Conversation).where(
        Conversation.knowledge_base_id == kb_id,
        Conversation.user_id == current_user.id,
    ))

    # 3. Delete all documents
    await db.execute(sa_delete(Document).where(Document.knowledge_base_id == kb_id))

    # 4. Delete the KB itself
    await db.delete(kb)
    await db.commit()
    await create_audit_log(
        db=db, operator_id=current_user.id, action="KNOWLEDGE_DELETE",
        target_type="knowledge_base", target_id=kb.id,
        detail={"name": kb.name}, status="SUCCESS",
    )
    logger.info(f"Knowledge base deleted: {kb.name} (id={kb.id}) by user {current_user.username}")
