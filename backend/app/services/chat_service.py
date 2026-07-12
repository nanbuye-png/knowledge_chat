import json
import time
from loguru import logger
from typing import AsyncGenerator, AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..prompts import get_prompt_provider
from ..prompts.base import BasePromptProvider
from ..prompts.resolver import resolve_prompt_provider
from ..schemas.chat import QueryResponse, SourceReference

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

    async def query_knowledge(
        self,
        question: str,
        knowledge_base_id: int,
        history: list[dict] = None,
        session: Optional[AsyncSession] = None,
    ) -> QueryResponse:
        """
        Query knowledge base with RAG and multi-turn context.

        1. Retrieve relevant documents via RetrievalPipeline
        2. Build messages with conversation history
        3. Call LLM with context + history
        4. Return answer with sources
        """
        t0 = time.monotonic()
        try:
            # 1. Retrieve relevant documents
            retrieval_result = await self._retrieval.retrieve(
                question=question,
                knowledge_base_id=knowledge_base_id,
            )

            if not retrieval_result.has_results:
                return QueryResponse(
                    answer="抱歉，当前知识库中暂无相关资料。",
                    has_knowledge=False,
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

            # 4. Call LLM via provider
            t_llm_start = time.monotonic()
            answer = await self._llm.chat(
                messages=messages,
                stream=False,
                temperature=0.7,
                max_tokens=2000,
            )
            logger.info(f"[TIMING] LLM call: {time.monotonic() - t_llm_start:.2f}s")
            logger.info(f"[TIMING] Total query_knowledge: {time.monotonic() - t0:.2f}s")

            # Convert sources to SourceReference for API response
            sources = [
                SourceReference(
                    document_id=s["document_id"],
                    filename=s["filename"],
                    chunk_index=s["chunk_index"],
                    text=s["text"],
                )
                for s in retrieval_result.sources
            ]

            return QueryResponse(answer=answer, sources=sources, has_knowledge=True)

        except Exception as e:
            logger.error(f"Knowledge query failed: {e}")
            return QueryResponse(
                answer=f"抱歉，查询过程中出现错误：{str(e)}",
                has_knowledge=False,
            )

    async def chat(self, message: str, history: list[dict] = None, session: Optional[AsyncSession] = None) -> str:
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

            return await self._llm.chat(
                messages=messages,
                stream=False,
                temperature=0.7,
                max_tokens=2000,
            )

        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return f"抱歉，对话出现错误：{str(e)}"

    async def stream_chat(self, message: str, history: list[dict] = None, session: Optional[AsyncSession] = None) -> AsyncGenerator[str, None]:
        """
        Stream chat response using SSE.
        Used for typewriter effect in frontend.
        """
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

            stream_response = await self._llm.chat(
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=2000,
            )
            if isinstance(stream_response, AsyncIterator):
                async for token in stream_response:
                    yield token

        except Exception as e:
            logger.error(f"Stream chat failed: {e}")
            yield f"抱歉，对话出现错误：{str(e)}"

    async def stream_query_knowledge(self, question: str, knowledge_base_id: int, history: list[dict] = None, session: Optional[AsyncSession] = None) -> AsyncGenerator[str, None]:
        """
        Stream knowledge base query response using SSE.
        First sends sources as JSON, then streams the answer.
        Uses conversation history for multi-turn context.
        """
        t0 = time.monotonic()
        try:
            logger.info(f"RAG query started: question='{question[:50]}...', kb_id={knowledge_base_id}, history_len={len(history) if history else 0}")

            # 1. Retrieve relevant documents
            try:
                retrieval_result = await self._retrieval.retrieve(
                    question=question,
                    knowledge_base_id=knowledge_base_id,
                )
            except Exception as e:
                logger.exception(f"Retrieval failed for query '{question[:50]}...': {e}")
                yield json.dumps({"type": "error", "message": "抱歉，检索文档时出现错误，请稍后重试。"}, ensure_ascii=False)
                return

            if not retrieval_result.has_results:
                yield json.dumps({
                    "type": "no_result",
                    "message": "抱歉，当前知识库中暂无相关资料。"
                }, ensure_ascii=False)
                return

            # 2. Send sources first
            yield json.dumps({"type": "sources", "sources": retrieval_result.sources}, ensure_ascii=False) + "\n"

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

            # 5. Stream LLM response via provider
            t_llm_start = time.monotonic()
            stream_response = await self._llm.chat(
                messages=messages,
                stream=True,
                temperature=0.3,
                max_tokens=2000,
            )
            if isinstance(stream_response, AsyncIterator):
                async for token in stream_response:
                    yield token

            logger.info(f"[TIMING] LLM stream duration: {time.monotonic() - t_llm_start:.2f}s")
            logger.info(f"[TIMING] Total stream_query_knowledge: {time.monotonic() - t0:.2f}s")

        except Exception as e:
            logger.exception(f"Stream knowledge query failed for kb_id={knowledge_base_id}, question='{question[:50]}...'")
            try:
                yield json.dumps({"type": "error", "message": "抱歉，查询过程中出现内部错误，请稍后重试。"}, ensure_ascii=False)
            except Exception:
                # If even the error yield fails, generator will simply end
                pass


# Singleton instance — prompt_provider obtained via factory; LLM provider is internal
chat_service = ChatService(
    prompt_provider=get_prompt_provider(),
)
