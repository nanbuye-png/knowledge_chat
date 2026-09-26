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
from ..services.message_service import create_user_message, create_assistant_message
from ..services.conversation_service import (
    auto_update_conversation_title,
    _verify_conversation_ownership,
)
from ..auth.deps import get_current_user
from ..auth.api_key import get_api_key_user
from ..core.rate_limit import rate_limit
from ..core.config import settings as app_settings
from ..storage.database import get_db, async_session
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
    """通用闲聊对话，调用当前配置的 LLM Provider。

    提供 conversation_id 时，会把用户消息与模型回答持久化到该会话。
    """
    await update_user_activity(db, current_user.id)
    logger.info(f"Chat message: {request.message[:100]}...")

    # 1. 校验会话归属并保存用户消息
    if request.conversation_id is not None:
        try:
            await _verify_conversation_ownership(db, request.conversation_id, current_user.id)
            await create_user_message(db, request.conversation_id, request.message)
            await auto_update_conversation_title(db, request.conversation_id, request.message)
        except ValueError:
            raise HTTPException(status_code=403, detail="无权访问该会话")
        except Exception:
            logger.exception(f"Failed to save user message for conversation_id={request.conversation_id}")
            return ChatResponse(answer="抱歉，消息保存失败，请稍后重试。")

    try:
        answer = await chat_service.chat(request.message, request.history)
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"对话失败: {str(e)}")

    # 2. 保存模型回答
    if request.conversation_id is not None:
        try:
            await create_assistant_message(db, request.conversation_id, answer)
        except Exception:
            logger.exception(f"Failed to save assistant message for conversation_id={request.conversation_id}")

    return ChatResponse(answer=answer)


@router.post("/stream", summary="流式对话（SSE）")
async def stream_chat(
    request: ChatRequest,
    current_user: User = Depends(_resolve_user),
):
    """SSE 流式对话接口。

    提供 conversation_id 时，会把用户消息与模型回答持久化到该会话。
    流式响应期间自行管理数据库会话（与 RAG 流式接口一致），
    避免请求级 session 的生命周期跨越整个流式输出。
    """
    logger.info(f"Stream chat: {request.message[:100]}...")

    async def generate():
        async with async_session() as db:
            full_answer = ""
            user_msg_saved = False
            await update_user_activity(db, current_user.id)

            # 1. 校验会话归属并保存用户消息
            if request.conversation_id is not None:
                try:
                    await _verify_conversation_ownership(db, request.conversation_id, current_user.id)
                    await create_user_message(db, request.conversation_id, request.message)
                    await auto_update_conversation_title(db, request.conversation_id, request.message)
                    user_msg_saved = True
                except ValueError:
                    yield f"data: {json.dumps({'token': '无权访问该会话'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                except Exception:
                    logger.exception(f"Failed to save user message for conversation_id={request.conversation_id}")
                    yield f"data: {json.dumps({'token': '抱歉，消息保存失败，请稍后重试。'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

            try:
                async for token in chat_service.stream_chat(request.message, request.history):
                    full_answer += token
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            except Exception:
                logger.exception("Stream chat generator failed")
                yield f"data: {json.dumps({'token': '抱歉，对话过程中出现内部错误，请稍后重试。'}, ensure_ascii=False)}\n\n"
                return

            # 2. 保存模型回答（与 RAG 一致：仅在真正拿到内容时保存）
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