import json
import time
from loguru import logger
from typing import AsyncGenerator, Optional

from ..core.config import settings
from ..prompts import get_prompt_provider
from ..prompts.base import BasePromptProvider
from ..providers.base import BaseLLMProvider
from ..providers import get_llm_provider
from ..models.document import Document, DocumentStatus
from ..schemas.chat import QueryResponse, SourceReference
from ..services.embedding_service import embedding_service
from ..storage.vector_store import vector_store


class ChatService:
    """Service for chat and Q&A operations.

    LLM calls are delegated to an injected :class:`BaseLLMProvider`.
    Prompt building is delegated to an injected :class:`BasePromptProvider`.
    This service no longer directly depends on ``AsyncOpenAI`` or
    hardcoded prompt strings.
    """

    def __init__(self, provider: BaseLLMProvider, prompt_provider: BasePromptProvider):
        """Initialize the chat service with injected dependencies.

        Args:
            provider: An LLM provider instance. Must be an instance of
                :class:`BaseLLMProvider`.
            prompt_provider: A prompt provider instance. Must be an
                instance of :class:`BasePromptProvider`.

        Raises:
            ValueError: If either dependency is not of the expected type.
        """
        if not isinstance(provider, BaseLLMProvider):
            raise ValueError(
                f"provider must be an instance of BaseLLMProvider, "
                f"got {type(provider).__name__}"
            )
        if not isinstance(prompt_provider, BasePromptProvider):
            raise ValueError(
                f"prompt_provider must be an instance of BasePromptProvider, "
                f"got {type(prompt_provider).__name__}"
            )
        self._current_mode = "knowledge"  # knowledge or chat
        self.provider = provider
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

    async def query_knowledge(self, question: str, knowledge_base_id: int, history: list[dict] = None) -> QueryResponse:
        """
        Query knowledge base with RAG and multi-turn context.
        
        1. Embed question
        2. Search vector store
        3. Build context from results
        4. Build messages with conversation history
        5. Call LLM with context + history
        6. Return answer with sources
        """
        t0 = time.monotonic()
        try:
            # 1. Generate query embedding
            t_embed_start = time.monotonic()
            query_embedding = await embedding_service.embed_query(question)
            logger.info(f"[TIMING] Embedding: {time.monotonic() - t_embed_start:.2f}s")
            if not query_embedding:
                return QueryResponse(
                    answer="抱歉，当前无法处理您的请求，请稍后再试。",
                    has_knowledge=False,
                )

            # 2. Search vector store (filtered by knowledge_base_id)
            t_search_start = time.monotonic()
            results = await vector_store.search(query_embedding, top_k=5, knowledge_base_id=knowledge_base_id)
            logger.info(f"[TIMING] Vector search: {time.monotonic() - t_search_start:.2f}s, results={len(results)}")

            if not results:
                return QueryResponse(
                    answer="抱歉，当前知识库中暂无相关资料。",
                    has_knowledge=False,
                )

            # Filter by score threshold
            min_score = 0.3
            relevant_results = [r for r in results if r.get("score", 0) >= min_score]

            if not relevant_results:
                return QueryResponse(
                    answer="抱歉，当前知识库中暂无相关资料。",
                    has_knowledge=False,
                )

            # 3. Build context
            context_parts = []
            sources = []

            for i, r in enumerate(relevant_results):
                context_parts.append(
                    f"[来源{i+1}] 文件名：{r['filename']} (段落{r['chunk_index']})\n"
                    f"内容：{r['text']}"
                )
                sources.append(SourceReference(
                    document_id=r["document_id"],
                    filename=r["filename"],
                    chunk_index=r["chunk_index"],
                    text=r["text"][:200],  # Truncate for display
                ))

            context = "\n\n".join(context_parts)
            system_prompt = self.prompt_provider.build_rag_prompt(context=context, question=question)

            # 4. Build messages with conversation history for multi-turn context
            messages = [{"role": "system", "content": system_prompt}]
            if history:
                for h in history[-10:]:  # Keep last 10 history messages
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })
            messages.append({"role": "user", "content": question})

            # 5. Call LLM via provider
            t_llm_start = time.monotonic()
            answer = await self.provider.chat(
                messages=messages,
                model=settings.LLM_MODEL,
                temperature=0.7,
                max_tokens=2000,
            )
            logger.info(f"[TIMING] LLM call: {time.monotonic() - t_llm_start:.2f}s")
            logger.info(f"[TIMING] Total query_knowledge: {time.monotonic() - t0:.2f}s")

            return QueryResponse(answer=answer, sources=sources, has_knowledge=True)

        except Exception as e:
            logger.error(f"Knowledge query failed: {e}")
            return QueryResponse(
                answer=f"抱歉，查询过程中出现错误：{str(e)}",
                has_knowledge=False,
            )

    async def chat(self, message: str, history: list[dict] = None) -> str:
        """
        General chat mode.
        Delegates to the LLM provider with conversation history.
        """
        try:
            messages = [{"role": "system", "content": self.prompt_provider.system_prompt}]

            # Add history
            if history:
                for h in history[-10:]:  # Keep last 10 messages
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })

            # Add current message
            messages.append({"role": "user", "content": message})

            return await self.provider.chat(
                messages=messages,
                model=settings.LLM_MODEL,
                temperature=0.7,
                max_tokens=2000,
            )

        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return f"抱歉，对话出现错误：{str(e)}"

    async def stream_chat(self, message: str, history: list[dict] = None) -> AsyncGenerator[str, None]:
        """
        Stream chat response using SSE.
        Used for typewriter effect in frontend.
        """
        try:
            messages = [{"role": "system", "content": self.prompt_provider.system_prompt}]

            if history:
                for h in history[-10:]:
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })

            messages.append({"role": "user", "content": message})

            async for token in self.provider.stream_chat(
                messages=messages,
                model=settings.LLM_MODEL,
                temperature=0.7,
                max_tokens=2000,
            ):
                yield token

        except Exception as e:
            logger.error(f"Stream chat failed: {e}")
            yield f"抱歉，对话出现错误：{str(e)}"

    async def stream_query_knowledge(self, question: str, knowledge_base_id: int, history: list[dict] = None) -> AsyncGenerator[str, None]:
        """
        Stream knowledge base query response using SSE.
        First sends sources as JSON, then streams the answer.
        Uses conversation history for multi-turn context.
        """
        t0 = time.monotonic()
        try:
            logger.info(f"RAG query started: question='{question[:50]}...', kb_id={knowledge_base_id}, history_len={len(history) if history else 0}")

            # Generate query embedding
            try:
                query_embedding = await embedding_service.embed_query(question)
            except Exception as embed_err:
                logger.exception(f"Embedding generation failed for query '{question[:50]}...'")
                yield json.dumps({"type": "error", "message": "抱歉，生成查询向量时出现错误，请稍后重试。"}, ensure_ascii=False)
                return

            if not query_embedding:
                yield json.dumps({"type": "error", "message": "无法处理请求"}, ensure_ascii=False)
                return

            # Search vector store (filtered by knowledge_base_id)
            try:
                results = await vector_store.search(query_embedding, top_k=5, knowledge_base_id=knowledge_base_id)
            except Exception as search_err:
                logger.exception(f"Vector search failed for kb_id={knowledge_base_id}")
                yield json.dumps({"type": "error", "message": "抱歉，向量检索时出现错误，请稍后重试。"}, ensure_ascii=False)
                return

            relevant_results = [r for r in results if r.get("score", 0) >= 0.3]

            if not relevant_results:
                # Try without filter to confirm data exists
                logger.warning(f"No results with kb filter (kb={knowledge_base_id}). Trying unfiltered for diagnosis...")
                try:
                    unfiltered = await vector_store.search(query_embedding, top_k=5)
                    logger.warning(f"Unfiltered search returned {len(unfiltered)} results. Their kb_ids: {[r.get('id', '?') for r in unfiltered[:3]]}")
                except Exception:
                    logger.warning("Unfiltered diagnostic search also failed, skipping.")

                yield json.dumps({
                    "type": "no_result",
                    "message": "抱歉，当前知识库中暂无相关资料。"
                }, ensure_ascii=False)
                return

            # Build context
            context_parts = []
            sources = []

            for i, r in enumerate(relevant_results):
                context_parts.append(
                    f"[来源{i+1}] 文件名：{r['filename']} (段落{r['chunk_index']})\n"
                    f"内容：{r['text']}"
                )
                sources.append({
                    "document_id": r["document_id"],
                    "filename": r["filename"],
                    "chunk_index": r["chunk_index"],
                    "text": r["text"][:200],
                })

            # Send sources first
            yield json.dumps({"type": "sources", "sources": sources}, ensure_ascii=False) + "\n"

            context = "\n\n".join(context_parts)
            system_prompt = self.prompt_provider.build_rag_prompt(context=context, question=question)

            # Build messages with conversation history for multi-turn context
            messages = [{"role": "system", "content": system_prompt}]
            if history:
                for h in history[-10:]:
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })
            messages.append({"role": "user", "content": question})

            # Stream LLM response via provider
            t_llm_start = time.monotonic()
            async for token in self.provider.stream_chat(
                messages=messages,
                model=settings.LLM_MODEL,
                temperature=0.3,
                max_tokens=2000,
            ):
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


# Singleton instance — provider and prompt_provider obtained via factories
chat_service = ChatService(
    provider=get_llm_provider(),
    prompt_provider=get_prompt_provider(),
)