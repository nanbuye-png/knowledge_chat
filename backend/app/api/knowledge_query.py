"""
Knowledge Query API — RAG 问答接口。

从 chat.py 中拆出的知识库问答相关端点。
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from ..schemas.chat import (
    QueryRequest, QueryResponse,
)
from ..services.chat_service import chat_service
from ..services.message_service import create_user_message, create_assistant_message
from ..services.conversation_service import auto_update_conversation_title, _verify_conversation_ownership
from ..models.knowledge_base import KnowledgeBase
from ..storage.database import get_db, async_session
from ..auth.deps import get_current_user
from ..core.rate_limit import rate_limit
from ..models.user import User
from ..services.user_service import update_user_activity

router = APIRouter(prefix="/api/knowledge", tags=["知识库问答"])


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


async def verify_conversation_knowledge_base(
    db: AsyncSession,
    conversation_id: int,
    knowledge_base_id: int,
    current_user: User,
):
    """知识库问答的前置校验：知识库归属 + 会话归属 + 两者一致性。

    审计 §6.2（IDOR）：此前只在 ``conversation_id is None`` 时才调用
    :func:`verify_knowledge_base_access`，于是「自己的会话 + 他人的
    ``knowledge_base_id``」可以越过归属校验直接检索别人的知识库。

    现在两条路径统一走这里：

    1. 知识库必须属于当前用户（否则 403）；
    2. 会话必须属于当前用户（否则 403）；
    3. 会话若已绑定知识库，必须与请求的知识库一致（否则 403）——
       这是纵深防御：避免「A 库的会话」被用来读写「B 库」的上下文。
    """
    await verify_knowledge_base_access(db, knowledge_base_id, current_user)

    try:
        conversation = await _verify_conversation_ownership(
            db, conversation_id, current_user.id
        )
    except ValueError:
        raise HTTPException(status_code=403, detail="无权访问该会话")

    bound_kb_id = conversation.knowledge_base_id
    if bound_kb_id is not None and bound_kb_id != knowledge_base_id:
        logger.warning(
            f"Knowledge base mismatch: conversation_id={conversation_id} "
            f"bound to kb={bound_kb_id} but request asked for kb={knowledge_base_id}"
        )
        raise HTTPException(status_code=403, detail="会话与知识库不匹配")

    return conversation


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="知识库问答",
    dependencies=[
        Depends(rate_limit(
            setting="RATE_LIMIT_CHAT",
            scope="chat",
            use_user=True,
        )),
    ],
)
async def query_knowledge(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """基于知识库进行问答检索，返回回答和引用来源。"""
    await update_user_activity(db, current_user.id)
    logger.info(f"Knowledge query: {request.question[:100]}...")

    # 审计 §6.2（IDOR）：知识库归属校验必须**无条件**执行。此前只在
    # conversation_id 为空时校验，于是「自己的会话 + 他人的 knowledge_base_id」
    # 可以绕过校验检索别人的知识库。
    if request.conversation_id is not None:
        await verify_conversation_knowledge_base(
            db, request.conversation_id, request.knowledge_base_id, current_user
        )
    else:
        await verify_knowledge_base_access(db, request.knowledge_base_id, current_user)

    # 校验通过后才写入用户消息（403 时不留任何副作用）
    if request.conversation_id is not None:
        try:
            await create_user_message(db, request.conversation_id, request.question)
            await auto_update_conversation_title(db, request.conversation_id, request.question)
        except ValueError:
            raise HTTPException(status_code=403, detail="无权访问该会话")
        except Exception:
            logger.exception(f"Failed to save user message for conversation_id={request.conversation_id}")
            return QueryResponse(
                answer="抱歉，消息保存失败，请稍后重试。",
                has_knowledge=False,
            )

    try:
        result = await chat_service.query_knowledge(
            request.question,
            request.knowledge_base_id,
            request.history,
            session=db,
            user_id=current_user.id,
            conversation_id=request.conversation_id,
        )
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

    if request.conversation_id is not None:
        try:
            await create_assistant_message(db, request.conversation_id, result.answer)
        except Exception:
            logger.exception(f"Failed to save assistant message for conversation_id={request.conversation_id}")

    return result


@router.post(
    "/query/stream",
    summary="流式知识库问答（SSE）",
    dependencies=[
        # Phase 3 §5.4：审计指出"加 /stream 即绕过限流"，这里补齐
        Depends(rate_limit(
            setting="RATE_LIMIT_CHAT",
            scope="chat_stream",
            use_user=True,
        )),
    ],
)
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

            # 审计 §6.2（IDOR）：流式路径同样无条件校验知识库归属
            # （此前只在 conversation_id 为空时校验）。
            if request.conversation_id is not None:
                try:
                    await verify_conversation_knowledge_base(
                        db, request.conversation_id, request.knowledge_base_id, current_user
                    )
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, str) else "无权访问该会话"
                    yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': detail}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                    return
            else:
                try:
                    await verify_knowledge_base_access(db, request.knowledge_base_id, current_user)
                except HTTPException:
                    yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': '无权访问该知识库'}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                    return

            if request.conversation_id is not None:
                try:
                    await create_user_message(db, request.conversation_id, request.question)
                    await auto_update_conversation_title(db, request.conversation_id, request.question)
                    user_msg_saved = True
                except Exception:
                    logger.exception(f"Failed to save user message for conversation_id={request.conversation_id}")
                    yield f"data: {json.dumps({'token': json.dumps({'type': 'error', 'message': '消息保存失败，请稍后重试。'}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
                    return

            try:
                async for data in chat_service.stream_query_knowledge(
                    request.question,
                    request.knowledge_base_id,
                    request.history,
                    session=db,
                    user_id=current_user.id,
                    conversation_id=request.conversation_id,
                ):
                    frame_type = None
                    try:
                        parsed = json.loads(data.strip())
                        if isinstance(parsed, dict) and "type" in parsed:
                            frame_type = parsed.get("type")
                            if frame_type == "no_result":
                                # §5.6：拒答也是一次"回答"。若只把它当控制帧丢掉，
                                # 历史会话里就只剩用户提问、看不到系统答了什么。
                                full_answer = parsed.get("message") or ""
                    except (json.JSONDecodeError, TypeError):
                        pass
                    if frame_type is None:
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