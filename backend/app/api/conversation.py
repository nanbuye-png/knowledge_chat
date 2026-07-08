from fastapi import APIRouter, HTTPException, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.chat import (
    CreateConversationRequest, CreateConversationResponse,
    ConversationListItem, MessageResponse,
    RenameConversationRequest, DeleteResponse,
)
from ..services.conversation_service import (
    create_conversation, get_conversations,
    delete_conversation, rename_conversation,
)
from ..services.message_service import get_messages_by_conversation
from ..storage.database import get_db

router = APIRouter(prefix="/api/conversations", tags=["会话管理"])


@router.post("", response_model=CreateConversationResponse, summary="创建会话")
async def create_conversation_endpoint(request: CreateConversationRequest, db: AsyncSession = Depends(get_db)):
    """创建一个新的聊天会话。"""
    try:
        conv = await create_conversation(db, request.knowledge_base_id)
        return CreateConversationResponse(
            id=conv["id"],
            title=conv["title"],
            knowledge_base_id=conv["knowledge_base_id"],
            created_at=conv["created_at"],
        )
    except Exception as e:
        logger.error(f"Create conversation failed: {e}")
        raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")


@router.get("", response_model=list[ConversationListItem], summary="获取会话列表")
async def list_conversations(knowledge_base_id: int, db: AsyncSession = Depends(get_db)):
    """获取指定知识库下的所有会话，按更新时间倒序排列。"""
    try:
        conversations = await get_conversations(db, knowledge_base_id)
        return [
            ConversationListItem(
                id=c["id"],
                title=c["title"],
                created_at=c["created_at"],
                updated_at=c["updated_at"],
            )
            for c in conversations
        ]
    except Exception as e:
        logger.error(f"List conversations failed: {e}")
        raise HTTPException(status_code=500, detail=f"获取会话列表失败: {str(e)}")


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse], summary="获取会话消息")
async def get_conversation_messages(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """获取指定会话的所有消息，按创建时间升序排列。"""
    try:
        messages = await get_messages_by_conversation(db, conversation_id)
        return [
            MessageResponse(
                id=m["id"],
                conversation_id=m["conversation_id"],
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
            )
            for m in messages
        ]
    except Exception as e:
        logger.error(f"Get conversation messages failed: {e}")
        raise HTTPException(status_code=500, detail=f"获取会话消息失败: {str(e)}")


@router.delete("/{conversation_id}", response_model=DeleteResponse, summary="删除会话")
async def delete_conversation_endpoint(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """删除指定会话。"""
    try:
        deleted = await delete_conversation(db, conversation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="会话不存在")
        return DeleteResponse(success=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete conversation failed: {e}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@router.patch("/{conversation_id}", response_model=ConversationListItem, summary="重命名会话")
async def rename_conversation_endpoint(
    conversation_id: int,
    request: RenameConversationRequest,
    db: AsyncSession = Depends(get_db),
):
    """重命名指定会话。"""
    try:
        conv = await rename_conversation(db, conversation_id, request.title)
        return ConversationListItem(
            id=conv["id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Rename conversation failed: {e}")
        raise HTTPException(status_code=500, detail=f"重命名会话失败: {str(e)}")
