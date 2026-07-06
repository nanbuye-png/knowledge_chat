from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
import json

from ..schemas.chat import (
    QueryRequest, QueryResponse,
    ChatRequest, ChatResponse,
    ModeResponse, ChatMode,
)
from ..services.chat_service import chat_service
from ..services.message_service import create_user_message, create_assistant_message
from ..storage.database import get_db

router = APIRouter(prefix="/api/chat", tags=["问答系统"])


@router.post("/query", response_model=QueryResponse, summary="知识库问答")
async def query_knowledge(request: QueryRequest, db: AsyncSession = Depends(get_db)):
    """基于知识库进行问答检索，返回回答和引用来源。"""
    logger.info(f"Knowledge query: {request.question[:100]}...")

    # Save user message if conversation_id is provided
    if request.conversation_id is not None:
        try:
            await create_user_message(db, request.conversation_id, request.question)
        except Exception:
            logger.exception(f"Failed to save user message for conversation_id={request.conversation_id}")
            return QueryResponse(
                answer="抱歉，消息保存失败，请稍后重试。",
                has_knowledge=False,
            )

    try:
        result = await chat_service.query_knowledge(request.question, request.knowledge_base_id)
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

    # Save assistant message if conversation_id is provided
    if request.conversation_id is not None:
        try:
            await create_assistant_message(db, request.conversation_id, result.answer)
        except Exception:
            logger.exception(f"Failed to save assistant message for conversation_id={request.conversation_id}")

    return result


@router.post("/chat", response_model=ChatResponse, summary="闲聊模式")
async def chat(request: ChatRequest):
    """通用闲聊对话，直接调用 DeepSeek API。"""
    logger.info(f"Chat message: {request.message[:100]}...")
    try:
        answer = await chat_service.chat(request.message, request.history)
        return ChatResponse(answer=answer)
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"对话失败: {str(e)}")


@router.post("/stream", summary="流式对话（SSE）")
async def stream_chat(request: ChatRequest):
    """
    SSE 流式对话接口。
    支持打字机效果，逐 token 返回响应。
    """
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


@router.post("/stream/query", summary="流式知识库问答（SSE）")
async def stream_query_knowledge(request: QueryRequest):
    """
    SSE 流式知识库问答接口。
    先返回引用来源（JSON），再逐 token 返回回答。
    """
    logger.info(f"Stream knowledge query: {request.question[:100]}...")

    async def generate():
        async for data in chat_service.stream_query_knowledge(request.question, request.knowledge_base_id):
            yield f"data: {json.dumps({'token': data}, ensure_ascii=False)}\n\n"
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


@router.put("/mode", response_model=ModeResponse, summary="切换模式")
async def set_mode(mode: ChatMode):
    """切换问答模式：knowledge（知识库）或 chat（闲聊）。"""
    try:
        await chat_service.set_mode(mode.mode)
        return ModeResponse(mode=mode.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Set mode failed: {e}")
        raise HTTPException(status_code=500, detail=f"切换模式失败: {str(e)}")


@router.get("/mode", response_model=ModeResponse, summary="获取当前模式")
async def get_mode():
    """获取当前问答模式。"""
    try:
        mode = await chat_service.get_mode()
        return ModeResponse(mode=mode)
    except Exception as e:
        logger.error(f"Get mode failed: {e}")
        raise HTTPException(status_code=500, detail="获取模式失败")
