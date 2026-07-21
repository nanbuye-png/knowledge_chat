"""
Chat API — 通用 AI 对话（非 RAG）。

RAG 知识库问答请使用 /api/knowledge/query 和 /api/knowledge/query/stream。
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
import json

from ..schemas.chat import (
    ChatRequest, ChatResponse,
)
from ..services.chat_service import chat_service
from ..auth.deps import get_current_user
from ..auth.api_key import get_api_key_user
from ..core.rate_limit import rate_limit
from ..core.config import settings as app_settings
from ..storage.database import get_db
from ..models.user import User
from ..services.user_service import update_user_activity

router = APIRouter(prefix="/api/chat", tags=["问答系统"])


async def _resolve_user(
    current_user: User | None = Depends(get_current_user),
    api_key_user: User | None = Depends(get_api_key_user),
) -> User:
    """支持 JWT 和 API Key 两种认证方式。"""
    user = current_user or api_key_user
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post("/chat", response_model=ChatResponse, summary="闲聊模式")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(_resolve_user),
    db: AsyncSession = Depends(get_db),
):
    """通用闲聊对话，调用当前配置的 LLM Provider。"""
    await update_user_activity(db, current_user.id)
    logger.info(f"Chat message: {request.message[:100]}...")
    try:
        answer = await chat_service.chat(request.message, request.history)
        return ChatResponse(answer=answer)
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"对话失败: {str(e)}")


@router.post("/stream", summary="流式对话（SSE）")
async def stream_chat(
    request: ChatRequest,
    current_user: User = Depends(_resolve_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式对话接口。"""
    await update_user_activity(db, current_user.id)
    logger.info(f"Stream chat: {request.message[:100]}...")

    async def generate():
        async for token in chat_service.stream_chat(request.message, request.history):
            yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )