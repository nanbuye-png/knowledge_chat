import json
import time
from loguru import logger
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.context import get_request_id
from ..core.retry import llm_policy, retry_async, retry_stream
from ..prompts import get_prompt_provider
from ..prompts.base import BasePromptProvider
from ..prompts.resolver import resolve_prompt_provider
from ..schemas.chat import QueryResponse, SourceReference
from .citation.validator import validate_citations
from .llm.base import LLMUsageInfo, call_with_usage, estimate_tokens
from .metrics import (
    track_abstention,
    track_llm_call,
    track_rag_stage,
)
from .retrieval.abstention import AbstentionDecision, create_abstention_decider
from .usage_service import usage_service

from .llm.factory import LLMProviderFactory
from .retrieval_pipeline import RetrievalPipeline


class ChatService:
    """Service for chat and Q&A operations.

    LLM calls are delegated to an internal :class:`DeepSeekProvider`.
    Prompt building is delegated to an injected :class:`BasePromptProvider`.
    Document retrieval is delegated to :class:`RetrievalPipeline`.
    This service no longer directly depends on ``AsyncOpenAI`` or
    hardcoded prompt strings.
    """

    def __init__(self, prompt_provider: BasePromptProvider):
        """Initialize the chat service with injected dependencies.

        Args:
            prompt_provider: A prompt provider instance. Must be an
                instance of :class:`BasePromptProvider`.

        Raises:
            ValueError: If the prompt_provider is not of the expected type.
        """
        if not isinstance(prompt_provider, BasePromptProvider):
            raise ValueError(
                f"prompt_provider must be an instance of BasePromptProvider, "
                f"got {type(prompt_provider).__name__}"
            )
        self._current_mode = "knowledge"  # knowledge or chat
        self._llm = LLMProviderFactory.create(settings)
        self._retrieval = RetrievalPipeline()
        self._abstention = create_abstention_decider()
        self.prompt_provider = prompt_provider

    async def get_mode(self) -> str:
        """Get current chat mode."""
        return self._current_mode

    async def set_mode(self, mode: str):
        """Set chat mode."""
        if mode not in ("knowledge", "chat"):
            raise ValueError("Invalid mode. Must be 'knowledge' or 'chat'")
        self._current_mode = mode
        logger.info(f"Chat mode switched to: {mode}")

    async def set_prompt_provider(self, prompt_provider: BasePromptProvider) -> None:
        """Replace the prompt provider for the current request.

        Args:
            prompt_provider: Any :class:`BasePromptProvider` instance.
        """
        if not isinstance(prompt_provider, BasePromptProvider):
            raise ValueError(
                f"prompt_provider must be an instance of BasePromptProvider, "
                f"got {type(prompt_provider).__name__}"
            )
        self.prompt_provider = prompt_provider

    async def get_prompt_provider(
        self, session: AsyncSession | None = None
    ) -> BasePromptProvider:
        """Return the active prompt provider for the current request.

        If *session* is provided, returns a :class:`DatabasePromptProvider`
        backed by that session (database templates take priority).  Otherwise
        returns the instance stored in ``self.prompt_provider``.

        Args:
            session: An optional async SQLAlchemy session.  When present,
                database templates are queried first.

        Returns:
            A :class:`BasePromptProvider` instance.
        """
        if session is not None:
            return resolve_prompt_provider(session)
        return self.prompt_provider

    @staticmethod
    async def _get_system_prompt(prompt_provider: BasePromptProvider) -> str:
        """Extract system prompt — supports both sync and async providers."""
        if hasattr(prompt_provider, "get_system_prompt"):
            return await prompt_provider.get_system_prompt()
        return prompt_provider.system_prompt

    @staticmethod
    async def _build_rag_prompt(
        prompt_provider: BasePromptProvider, context: str, question: str
    ) -> str:
        """Build RAG prompt — supports both sync and async providers."""
        if hasattr(prompt_provider, "get_rag_prompt"):
            return await prompt_provider.get_rag_prompt(context=context, question=question)
        return prompt_provider.build_rag_prompt(context=context, question=question)

    # ------------------------------------------------------------------
    # LLM 调用（Phase 3 §5.2：统一重试）
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: list[dict], **kwargs) -> str:
        """非流式 LLM 调用，按 ``LLM_RETRY_*`` 策略重试瞬时错误。

        返回 ``str``：provider 返回非字符串（异常形状）时降级为空串，
        由上层把空回答当作失败处理，而不是把对象塞进回答。
        """
        text, _ = await self._call_llm_with_usage(messages, **kwargs)
        return text

    async def _call_llm_with_usage(
        self, messages: list[dict], **kwargs
    ) -> tuple[str, LLMUsageInfo]:
        """非流式 LLM 调用，同时拿到 provider 透出的 usage（审计 §3.4）。"""
        start = time.perf_counter()
        response, usage = await retry_async(
            lambda: call_with_usage(self._llm, messages, **kwargs),
            policy=llm_policy(),
            operation="llm.chat",
        )
        if not usage.latency_ms:
            usage.latency_ms = (time.perf_counter() - start) * 1000
        return (response if isinstance(response, str) else ""), usage

    async def _record_usage(
        self,
        usage: LLMUsageInfo,
        *,
        session: Optional[AsyncSession] = None,
        user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> None:
        """上报 LLM 指标，并在拿到会话/用户时落库到 ``llm_usages``。

        审计 §3.4：``usage_service.record`` 在生产代码里**零调用点**，
        导致 llm_usages 永远为空、前端 Token/成本页面恒为 0。这里接上写入端；
        计费/统计失败绝不影响问答（只 warning）。
        """
        model = usage.model or settings.LLM_MODEL
        track_llm_call(
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency=usage.latency_ms / 1000.0,
        )

        if session is None or user_id is None:
            return

        try:
            await usage_service.record(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                provider=settings.LLM_PROVIDER,
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                latency_ms=round(usage.latency_ms, 2),
            )
        except Exception as exc:  # noqa: BLE001 - 统计不能影响主链路
            logger.warning(f"记录 LLM 用量失败: {type(exc).__name__}: {exc}")

    @staticmethod
    def _estimate_stream_usage(prompt_text: str, answer_text: str, latency_ms: float) -> LLMUsageInfo:
        """流式调用没有可用 usage → 用启发式估算并明确标记 ``estimated``。

        审计 §3.4 指出 usage 端到端缺失；流式是主链路（前端打字机效果），
        若完全不计，Token 统计仍然等于没有。
        """
        return LLMUsageInfo(
            model=settings.LLM_MODEL,
            prompt_tokens=estimate_tokens(prompt_text),
            completion_tokens=estimate_tokens(answer_text),
            latency_ms=latency_ms,
            estimated=True,
        )

    async def _stream_llm(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式 LLM 调用，只重试"首字节之前"的失败。

        一旦已经向客户端吐出 token，就不再重试 —— 否则前端会把已渲染的
        内容重复追加一遍。语义细节见 :func:`app.core.retry.retry_stream`。
        """
        async for token in retry_stream(
            lambda: self._llm.chat(messages=messages, stream=True, **kwargs),
            policy=llm_policy(),
            operation="llm.stream",
        ):
            yield token

    async def query_knowledge(
        self,
        question: str,
        knowledge_base_id: int,
        history: list[dict] = None,
        session: Optional[AsyncSession] = None,
        *,
        user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> QueryResponse:
        """
        Query knowledge base with RAG and multi-turn context.

        1. Retrieve relevant documents via RetrievalPipeline
        2. Build messages with conversation history
        3. Call LLM with context + history
        4. Return answer with sources

        Args:
            user_id / conversation_id: 提供时把本次调用的 token 用量写入
                ``llm_usages``（审计 §3.4：写入端此前完全缺失）。
        """
        t0 = time.monotonic()
        try:
            # 1. Retrieve relevant documents（§5.6：检索总耗时单列，便于与子阶段对齐）
            t_retrieval = time.monotonic()
            retrieval_result = await self._retrieval.retrieve(
                question=question,
                knowledge_base_id=knowledge_base_id,
                history=history,
            )
            track_rag_stage("retrieval_total", time.monotonic() - t_retrieval)

            # §5.6：无足够依据 → 拒答（不调用 LLM，避免无依据生成）
            # 无上下文（no_context）也走这里，文案由 ABSTENTION_MESSAGE 配置
            abstention = self._abstention.decide(retrieval_result)
            if abstention.should_abstain:
                logger.info(
                    f"知识库问答拒答: reason={abstention.reason}, "
                    f"details={abstention.details}"
                )
                track_abstention(abstention.reason)
                return QueryResponse(
                    answer=abstention.message,
                    has_knowledge=False,
                    abstained=True,
                    abstention_reason=abstention.reason,
                )

            # 2. Build RAG prompt with retrieved context
            prompt_provider = await self.get_prompt_provider(session)
            system_prompt = await self._build_rag_prompt(
                prompt_provider, retrieval_result.context, question
            )

            # 3. Build messages with conversation history for multi-turn context
            messages = [{"role": "system", "content": system_prompt}]
            if history:
                for h in history[-10:]:  # Keep last 10 history messages
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })
            messages.append({"role": "user", "content": question})

            # 4. Call LLM via provider（Phase 3 §5.2：瞬时错误自动重试）
            t_llm_start = time.monotonic()
            answer, usage = await self._call_llm_with_usage(
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
            )
            llm_seconds = time.monotonic() - t_llm_start
            track_rag_stage("llm", llm_seconds)
            await self._record_usage(
                usage,
                session=session,
                user_id=user_id,
                conversation_id=conversation_id,
            )
            logger.info(
                f"[TIMING] LLM call: {llm_seconds:.2f}s "
                f"(prompt_tokens={usage.prompt_tokens}, "
                f"completion_tokens={usage.completion_tokens}, estimated={usage.estimated})"
            )
            logger.info(
                f"[TIMING] Total query_knowledge: {time.monotonic() - t0:.2f}s "
                f"request_id={get_request_id()}"
            )

            # Convert sources to SourceReference for API response
            sources = [
                SourceReference(
                    document_id=s["document_id"],
                    filename=s["filename"],
                    chunk_index=s["chunk_index"],
                    text=s["text"],
                    page=s.get("page"),
                    section=s.get("section"),
                )
                for s in retrieval_result.sources
            ]

            # §5.5：结构化引用 + 一致性校验（禁止模型自造引用）
            citations = [c.to_dict() for c in retrieval_result.citations]
            validation = validate_citations(
                retrieval_result.citations,
                retrieval_result.results,
                answer=answer,
            )
            if validation.has_fabricated_references:
                logger.warning(
                    f"答案引用了不存在的来源编号: {validation.invalid_reference_indices}"
                )

            return QueryResponse(
                answer=answer,
                sources=sources,
                citations=citations,
                has_knowledge=True,
            )

        except Exception as e:
            # 失败必须与"拒答"区分开，并且**不能把内部异常原文当成回答**：
            # 那既泄漏 provider 报文，又会让调用方（前端/评测）
            # 把故障当成模型回答。抱歉文案只给用户看，细节进 error 与日志。
            logger.error(f"Knowledge query failed: {type(e).__name__}: {e}")
            return QueryResponse(
                answer="抱歉，服务暂时不可用，请稍后重试。",
                has_knowledge=False,
                error=f"{type(e).__name__}: {e}",
            )

    async def chat(
        self,
        message: str,
        history: list[dict] = None,
        session: Optional[AsyncSession] = None,
        *,
        user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> str:
        """
        General chat mode.
        Delegates to the LLM provider with conversation history.
        """
        try:
            prompt_provider = await self.get_prompt_provider(session)
            system_prompt = await self._get_system_prompt(prompt_provider)

            messages = [{"role": "system", "content": system_prompt}]

            # Add history
            if history:
                for h in history[-10:]:  # Keep last 10 messages
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })

            # Add current message
            messages.append({"role": "user", "content": message})

            answer, usage = await self._call_llm_with_usage(
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
            )
            await self._record_usage(
                usage,
                session=session,
                user_id=user_id,
                conversation_id=conversation_id,
            )
            return answer

        except Exception as e:
            # 同上：不要把 provider 异常原文当回答返回给用户
            logger.error(f"Chat failed: {type(e).__name__}: {e}")
            return "抱歉，服务暂时不可用，请稍后重试。"

    async def _finish_stream_usage(
        self,
        prompt_text: str,
        answer_text: str,
        started_at: float,
        *,
        session: Optional[AsyncSession],
        user_id: Optional[int],
        conversation_id: Optional[int],
    ) -> None:
        """流式收尾：估算 usage 并记录（失败/取消都不影响已发出的响应）。"""
        try:
            usage = self._estimate_stream_usage(
                prompt_text, answer_text, (time.monotonic() - started_at) * 1000
            )
            await self._record_usage(
                usage,
                session=session,
                user_id=user_id,
                conversation_id=conversation_id,
            )
        except Exception as exc:  # noqa: BLE001 - 统计失败不影响回答
            logger.debug(f"流式用量记录跳过: {exc}")

    async def stream_chat(
        self,
        message: str,
        history: list[dict] = None,
        session: Optional[AsyncSession] = None,
        *,
        user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat response using SSE.
        Used for typewriter effect in frontend.
        """
        started_at = time.monotonic()
        prompt_text = ""
        answer_parts: list[str] = []
        try:
            prompt_provider = await self.get_prompt_provider(session)
            system_prompt = await self._get_system_prompt(prompt_provider)

            messages = [{"role": "system", "content": system_prompt}]

            if history:
                for h in history[-10:]:
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })

            messages.append({"role": "user", "content": message})
            prompt_text = "\n".join(
                m.get("content", "") for m in messages if isinstance(m.get("content"), str)
            )

            # Phase 3 §5.2：流式调用只重试首字节前的失败
            async for token in self._stream_llm(
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
            ):
                answer_parts.append(token)
                yield token

        except Exception as e:
            logger.error(f"Stream chat failed: {e}")
            yield f"抱歉，对话出现错误：{str(e)}"
        finally:
            await self._finish_stream_usage(
                prompt_text,
                "".join(answer_parts),
                started_at,
                session=session,
                user_id=user_id,
                conversation_id=conversation_id,
            )

    async def stream_query_knowledge(
        self,
        question: str,
        knowledge_base_id: int,
        history: list[dict] = None,
        session: Optional[AsyncSession] = None,
        *,
        user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream knowledge base query response using SSE.
        First sends sources as JSON, then streams the answer.
        Uses conversation history for multi-turn context.
        """
        t0 = time.monotonic()
        started_at = time.monotonic()
        prompt_text = ""
        answer_parts: list[str] = []
        try:
            logger.info(
                f"RAG query started: question='{question[:50]}...', "
                f"kb_id={knowledge_base_id}, "
                f"history_len={len(history) if history else 0}, "
                f"request_id={get_request_id()}"
            )

            # 1. Retrieve relevant documents
            t_retrieval = time.monotonic()
            try:
                retrieval_result = await self._retrieval.retrieve(
                    question=question,
                    knowledge_base_id=knowledge_base_id,
                    history=history,
                )
            except Exception as e:
                logger.exception(f"Retrieval failed for query '{question[:50]}...': {e}")
                yield json.dumps({"type": "error", "message": "抱歉，检索文档时出现错误，请稍后重试。"}, ensure_ascii=False)
                return
            track_rag_stage("retrieval_total", time.monotonic() - t_retrieval)

            # §5.6：无足够依据 → 拒答（不调用 LLM）
            # 复用 no_result 控制帧以保持前端契约兼容，额外字段携带拒答信号与 Debug 信息
            abstention = self._abstention.decide(retrieval_result)
            if abstention.should_abstain:
                logger.info(
                    f"知识库问答拒答: reason={abstention.reason}, "
                    f"details={abstention.details}"
                )
                track_abstention(abstention.reason)
                yield json.dumps(
                    {
                        "type": "no_result",
                        "message": abstention.message,
                        **abstention.to_dict(),
                    },
                    ensure_ascii=False,
                ) + "\n"
                return

            # 2. Send sources + structured citations first（§5.5）
            yield json.dumps(
                {
                    "type": "sources",
                    "sources": retrieval_result.sources,
                    "citations": [c.to_dict() for c in retrieval_result.citations],
                },
                ensure_ascii=False,
            ) + "\n"

            # 3. Build RAG prompt with retrieved context
            prompt_provider = await self.get_prompt_provider(session)
            system_prompt = await self._build_rag_prompt(
                prompt_provider, retrieval_result.context, question
            )

            # 4. Build messages with conversation history for multi-turn context
            messages = [{"role": "system", "content": system_prompt}]
            if history:
                for h in history[-10:]:
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })
            messages.append({"role": "user", "content": question})
            prompt_text = "\n".join(
                m.get("content", "") for m in messages if isinstance(m.get("content"), str)
            )

            # 5. Stream LLM response via provider（带重试：首字节前失败可重试）
            t_llm_start = time.monotonic()
            async for token in self._stream_llm(
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
            ):
                answer_parts.append(token)
                yield token

            llm_seconds = time.monotonic() - t_llm_start
            track_rag_stage("llm", llm_seconds)
            logger.info(
                f"[TIMING] LLM stream duration: {llm_seconds:.2f}s "
                f"(chars={len(''.join(answer_parts))})"
            )
            logger.info(
                f"[TIMING] Total stream_query_knowledge: {time.monotonic() - t0:.2f}s "
                f"request_id={get_request_id()}"
            )

        except Exception as e:
            logger.exception(f"Stream knowledge query failed for kb_id={knowledge_base_id}, question='{question[:50]}...'")
            try:
                yield json.dumps({"type": "error", "message": "抱歉，查询过程中出现内部错误，请稍后重试。"}, ensure_ascii=False)
            except Exception:
                # If even the error yield fails, generator will simply end
                pass
        finally:
            await self._finish_stream_usage(
                prompt_text,
                "".join(answer_parts),
                started_at,
                session=session,
                user_id=user_id,
                conversation_id=conversation_id,
            )


# Singleton instance — prompt_provider obtained via factory; LLM provider is internal
chat_service = ChatService(
    prompt_provider=get_prompt_provider(),
)
