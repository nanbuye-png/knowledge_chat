from fastapi import APIRouter, HTTPException, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.chat import CreateConversationRequest, CreateConversationResponse, ConversationListItem
from ..services.conversation_service import create_conversation, get_conversations
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
