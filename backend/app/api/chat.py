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
from ..models.knowledge_base import KnowledgeBase
from ..storage.database import get_db, async_session
from ..auth.deps import get_current_user
from ..auth.api_key import get_api_key_user
from ..core.rate_limit import rate_limit
from ..core.config import settings as app_settings
from ..models.user import User
from ..services.user_service import update_user_activity
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


async def verify_knowledge_base_access(
    db: AsyncSession,
    knowledge_base_id: int,
    current_user: User,
) -> KnowledgeBase:
    """Verify the knowledge base belongs to the current user. Raises HTTPException if not."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=403, detail="无权访问该知识库")
    return kb


async def _resolve_user(
    current_user: User | None = Depends(get_current_user),
    api_key_user: User | None = Depends(get_api_key_user),
) -> User:
    """支持 JWT 和 API Key 两种认证方式。"""
    user = current_user or api_key_user
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="知识库问答",
    dependencies=[
        Depends(rate_limit(
            limit=app_settings.RATE_LIMIT_CHAT,
            window_seconds=app_settings.RATE_LIMIT_WINDOW,
            scope="chat",
            use_user=True,
        )),
    ],
)
async def query_knowledge(
    request: QueryRequest,
    current_user: User = Depends(_resolve_user),
    db: AsyncSession = Depends(get_db),
):
    """基于知识库进行问答检索，返回回答和引用来源。"""
    await update_user_activity(db, current_user.id)
    logger.info(f"Knowledge query: {request.question[:100]}...")

    # Save user message if conversation_id is provided
    if request.conversation_id is not None:
        try:
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

    if request.conversation_id is None:
        await verify_knowledge_base_access(db, request.knowledge_base_id, current_user)

    try:
        result = await chat_service.query_knowledge(request.question, request.knowledge_base_id, request.history, session=db)
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

    if request.conversation_id is not None:
        try:
            await create_assistant_message(db, request.conversation_id, result.answer)
        except Exception:
            logger.exception(f"Failed to save assistant message for conversation_id={request.conversation_id}")

    return result


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


@router.post("/stream/query", summary="流式知识库问答（SSE）")
async def stream_query_knowledge(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
):
    """SSE 流式知识库问答接口。"""
    logger.info(f"Stream knowledge query: {request.question[:100]}...")

    async def generate():
        async with async_session() as db:
            full_answer = ""
            user_msg_saved = False
            await update_user_activity(db, current_user.id)

            if request.conversation_id is not None:
                try:
                    await _verify_conversation_ownership(db, request.conversation_id, current_user.id)
                    await create_user_message(db, request.conversation_id, request.question)
                    await _auto_update_title(db, request.conversation_id, request.question)
                    user_msg_saved = True
                except ValueError:
                    yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': '无权访问该会话'}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                    return
                except Exception:
                    logger.exception(f"Failed to save user message for conversation_id={request.conversation_id}")
                    yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': '消息保存失败，请稍后重试。'}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                    return

            if request.conversation_id is None:
                try:
                    await verify_knowledge_base_access(db, request.knowledge_base_id, current_user)
                except HTTPException:
                    yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': '无权访问该知识库'}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                    return

            try:
                async for data in chat_service.stream_query_knowledge(
                    request.question, request.knowledge_base_id, request.history, session=db
                ):
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

            if request.conversation_id is not None and user_msg_saved and full_answer.strip():
                try:
                    await create_assistant_message(db, request.conversation_id, full_answer)
                except Exception:
                    logger.exception(f"Failed to save assistant message for conversation_id={request.conversation_id}")

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
async def set_mode(
    mode: ChatMode,
    current_user: User = Depends(get_current_user),
):
    """切换问答模式。"""
    try:
        await chat_service.set_mode(mode.mode)
        return ModeResponse(mode=mode.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Set mode failed: {e}")
        raise HTTPException(status_code=500, detail=f"切换模式失败: {str(e)}")


@router.get("/mode", response_model=ModeResponse, summary="获取当前模式")
async def get_mode(
    current_user: User = Depends(get_current_user),
):
    """获取当前问答模式。"""
    try:
        mode = await chat_service.get_mode()
        return ModeResponse(mode=mode)
    except Exception as e:
        logger.error(f"Get mode failed: {e}")
        raise HTTPException(status_code=500, detail="获取模式失败")