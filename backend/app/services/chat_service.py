import json
from loguru import logger
from typing import AsyncGenerator, Optional
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.config import settings
from ..models.document import Document, DocumentStatus
from ..schemas.chat import QueryResponse, SourceReference
from ..services.embedding_service import embedding_service
from ..storage.vector_store import vector_store


SYSTEM_PROMPT_KNOWLEDGE = """你是一个专业的智能知识库问答助手，名为"智问"。
请基于以下参考资料回答问题。回答需要：
1. 准确、简洁、有条理
2. 标注引用来源（使用文件名+段落索引格式）
3. 如果参考资料不足以回答问题，请明确告知
4. 使用中文回答

参考资料：
{context}"""

SYSTEM_PROMPT_CHAT = """你是一个智能AI助手，名为"智问"。
你的特点：
1. 友好、专业、热情
2. 回答简洁明了
3. 能够进行多轮对话
4. 使用中文回答"""


class ChatService:
    """Service for chat and Q&A operations."""

    def __init__(self):
        self._current_mode = "knowledge"  # knowledge or chat
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client for DeepSeek."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_API_BASE,
            )
        return self._client

    async def get_mode(self) -> str:
        """Get current chat mode."""
        return self._current_mode

    async def set_mode(self, mode: str):
        """Set chat mode."""
        if mode not in ("knowledge", "chat"):
            raise ValueError("Invalid mode. Must be 'knowledge' or 'chat'")
        self._current_mode = mode
        logger.info(f"Chat mode switched to: {mode}")

    async def query_knowledge(self, question: str, knowledge_base_id: int) -> QueryResponse:
        """
        Query knowledge base with RAG.
        
        1. Embed question
        2. Search vector store
        3. Build context from results
        4. Call LLM with context
        5. Return answer with sources
        """
        try:
            # 1. Generate query embedding
            query_embedding = await embedding_service.embed_query(question)
            if not query_embedding:
                return QueryResponse(
                    answer="抱歉，当前无法处理您的请求，请稍后再试。",
                    has_knowledge=False,
                )

            # 2. Search vector store (filtered by knowledge_base_id)
            results = await vector_store.search(query_embedding, top_k=5, knowledge_base_id=knowledge_base_id)

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
            system_prompt = SYSTEM_PROMPT_KNOWLEDGE.format(context=context)

            # 4. Call LLM
            answer = await self._call_llm(system_prompt, question)

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
        Calls DeepSeek API directly with conversation history.
        """
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT_CHAT}]

            # Add history
            if history:
                for h in history[-10:]:  # Keep last 10 messages
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })

            # Add current message
            messages.append({"role": "user", "content": message})

            return await self._call_llm(messages=messages)

        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return f"抱歉，对话出现错误：{str(e)}"

    async def stream_chat(self, message: str, history: list[dict] = None) -> AsyncGenerator[str, None]:
        """
        Stream chat response using SSE.
        Used for typewriter effect in frontend.
        """
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT_CHAT}]

            if history:
                for h in history[-10:]:
                    messages.append({
                        "role": h.get("role", "user"),
                        "content": h.get("content", ""),
                    })

            messages.append({"role": "user", "content": message})

            client = self._get_client()
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Stream chat failed: {e}")
            yield f"抱歉，对话出现错误：{str(e)}"

    async def stream_query_knowledge(self, question: str, knowledge_base_id: int) -> AsyncGenerator[str, None]:
        """
        Stream knowledge base query response using SSE.
        First sends sources as JSON, then streams the answer.
        """
        stream = None
        try:
            logger.info(f"RAG query started: question='{question[:50]}...', kb_id={knowledge_base_id}")

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
            system_prompt = SYSTEM_PROMPT_KNOWLEDGE.format(context=context)

            # Stream LLM response
            client = self._get_client()
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                temperature=0.3,
                max_tokens=2000,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.exception(f"Stream knowledge query failed for kb_id={knowledge_base_id}, question='{question[:50]}...'")
            try:
                yield json.dumps({"type": "error", "message": "抱歉，查询过程中出现内部错误，请稍后重试。"}, ensure_ascii=False)
            except Exception:
                # If even the error yield fails, generator will simply end
                pass
        finally:
            # Ensure the stream is properly closed to release resources.
            # Note: OpenAI SDK v1.x AsyncStream.close() is a synchronous method
            # (it closes the underlying httpx response), so no await is needed.
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    async def _call_llm(self, system_prompt: str = None, user_message: str = None, messages: list = None) -> str:
        """Call DeepSeek LLM."""
        try:
            client = self._get_client()

            if messages is None:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ]

            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise


# Singleton instance
chat_service = ChatService()