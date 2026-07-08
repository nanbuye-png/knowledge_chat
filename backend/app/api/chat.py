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
from ..services.conversation_service import update_conversation_title, _verify_conversation_ownership
from ..models.conversation import Conversation
from ..storage.database import get_db, async_session
from ..auth.deps import get_current_user
from ..models.user import User
from sqlalchemy import select

router = APIRouter(prefix="/api/chat", tags=["问答系统"])

DEFAULT_TITLES = {"New Chat", "新对话"}


def _generate_title(text: str, max_length: int = 30) -> str:
    """Generate a conversation title from the first user message."""
    title = text.strip()
    if len(title) > max_length:
        title = title[:max_length]
    return title


async def _auto_update_title(db: AsyncSession, conversation_id: int, text: str):
    """Update conversation title from the first user message if it's still the default."""
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return
    if conversation.title in DEFAULT_TITLES:
        new_title = _generate_title(text)
        try:
            await update_conversation_title(db, conversation_id, new_title)
        except Exception:
            logger.exception(f"Failed to auto-update title for conversation_id={conversation_id}")


@router.post("/query", response_model=QueryResponse, summary="知识库问答")
async def query_knowledge(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """基于知识库进行问答检索，返回回答和引用来源。"""
    logger.info(f"Knowledge query: {request.question[:100]}...")

    # Save user message if conversation_id is provided
    if request.conversation_id is not None:
        try:
            # Verify conversation ownership before saving
            await _verify_conversation_ownership(db, request.conversation_id, current_user.id)
            await create_user_message(db, request.conversation_id, request.question)
            await _auto_update_title(db, request.conversation_id, request.question)
        except ValueError:
            raise HTTPException(status_code=403, detail="无权访问该会话")
        except Exception:
            logger.exception(f"Failed to save user message for conversation_id={request.conversation_id}")
            return QueryResponse(
                answer="抱歉，消息保存失败，请稍后重试。",
                has_knowledge=False,
            )

    try:
        result = await chat_service.query_knowledge(request.question, request.knowledge_base_id, request.history)
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
async def stream_query_knowledge(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
):
    """
    SSE 流式知识库问答接口。
    先返回引用来源（JSON），再逐 token 返回回答。
    若提供 conversation_id，会在流开始前保存用户消息，流结束后保存完整的助理回复。
    """
    logger.info(f"Stream knowledge query: {request.question[:100]}...")

    async def generate():
        # Manually manage DB session for StreamingResponse generator lifetime.
        # Depends(get_db) is not suitable here because the session would be closed
        # before the async generator finishes.
        async with async_session() as db:
            full_answer = ""
            user_msg_saved = False

            # ---- Before streaming: save user message ----
            if request.conversation_id is not None:
                try:
                    # Verify conversation ownership before saving
                    await _verify_conversation_ownership(db, request.conversation_id, current_user.id)
                    await create_user_message(db, request.conversation_id, request.question)
                    await _auto_update_title(db, request.conversation_id, request.question)
                    user_msg_saved = True
                except ValueError:
                    yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': '无权访问该会话'}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                    return
                except Exception:
                    logger.exception(
                        f"Failed to save user message for conversation_id={request.conversation_id}"
                    )
                    yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': '消息保存失败，请稍后重试。'}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                    return

            # ---- During streaming: accumulate assistant content ----
            try:
                async for data in chat_service.stream_query_knowledge(
                    request.question, request.knowledge_base_id, request.history
                ):
                    # Distinguish plain-text tokens from control JSON messages
                    # (sources / error / no_result).  Control messages must not be
                    # included in the persisted assistant content.
                    is_control = False
                    try:
                        parsed = json.loads(data.strip())
                        if isinstance(parsed, dict) and "type" in parsed:
                            is_control = True
                    except (json.JSONDecodeError, TypeError):
                        pass

                    if not is_control:
                        full_answer += data

                    yield f"data: {json.dumps({'token': data}, ensure_ascii=False)}\n\n"

            except Exception:
                logger.exception("Stream query generator failed")
                yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': '查询过程中出现内部错误，请稍后重试。'}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                return

            # ---- Before [DONE]: save assistant message ----
            if request.conversation_id is not None and user_msg_saved and full_answer.strip():
                try:
                    await create_assistant_message(db, request.conversation_id, full_answer)
                except Exception:
                    logger.exception(
                        f"Failed to save assistant message for conversation_id={request.conversation_id}"
                    )

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
