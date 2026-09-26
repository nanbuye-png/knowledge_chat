"""Retrieval Pipeline — decouples document retrieval from ChatService.

Provides a single entry-point for RAG retrieval steps:
1. Embed the user query
2. Search the vector store
3. Score‑filter & build context

Future extensions (hybrid search, reranker, citation) will be injected
into this pipeline without affecting ChatService.
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from ..services.citation.builder import CitationBuilder
from ..services.embedding_service import embedding_service
from ..core.config import settings
from ..storage.database import async_session
from .knowledge.runtime_config import KnowledgeRuntimeConfigService
from .query.factory import create_query_rewriter
from .retrieval.factory import RetrieverFactory
from .retrieval.models import RetrievalResult
from .retrieval.reranker import create_reranker_service

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class RetrievalPipeline:
    """Orchestrates RAG document retrieval independently of ChatService.

    Usage::

        pipeline = RetrievalPipeline()
        result = await pipeline.retrieve("什么是知识库？", knowledge_base_id=1)
        if result.has_results:
            # result.context  → prompt-ready string
            # result.sources  → frontend display
            ...
    """

    # Configuration (overridable via __init__ or subclasses)
    _top_k: int = 5
    _min_score: float = 0.3

    def __init__(self) -> None:
        self._retriever = RetrieverFactory.create()
        self._runtime_config_service = KnowledgeRuntimeConfigService()
        self._citation_builder = CitationBuilder()
        self._rewriter = create_query_rewriter()
        self._reranker = create_reranker_service()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        question: str,
        knowledge_base_id: int,
        top_k: int | None = None,
        min_score: float | None = None,
        history: list[dict] | None = None,
    ) -> RetrievalResult:
        """Run the full retrieval pipeline for a single query.

        Steps:
            0. Query Rewrite — 生成检索用查询（失败自动回退原始 Query）。
            1. Embed *search query* via :func:`embedding_service.embed_query`.
            2. Delegate to :class:`BaseRetriever` for vector search.
            3. Score‑filter results.
            4. Build concatenated context + source list.

        Args:
            question: The user's natural‑language question (原始提问，永不改写).
            knowledge_base_id: Restrict search to this knowledge base.
            top_k: Override default retrieval count (default 5).
            min_score: Override default score threshold (default 0.3).
            history: 对话历史，用于 Query Rewrite 补全指代与省略主语。

        Returns:
            A :class:`RetrievalResult` containing results, context, sources,
            citations, the original/search query pair and the rewrite status.
        """
        min_score = min_score if min_score is not None else self._min_score

        # Resolve top_k: caller override → per‑KB config → default (5)
        if top_k is None:
            async with async_session() as session:
                runtime_config = await self._runtime_config_service.resolve(
                    session, knowledge_base_id
                )
            top_k = runtime_config.retrieval_top_k
        else:
            logger.debug(f"Using caller‑supplied top_k={top_k}")

        # 0. Query Rewrite（永不抛异常，失败即回退）
        rewrite = await self._rewriter.rewrite(question, history)
        search_query = rewrite.rewritten_query or question
        logger.info(
            f"Query rewrite: status={rewrite.rewrite_status}, "
            f"latency={rewrite.latency_ms:.0f}ms, "
            f"original='{question[:40]}', search='{search_query[:40]}'"
            + (f", error={rewrite.error}" if rewrite.error else "")
        )

        base_metadata = {"rewrite": rewrite.to_dict()}

        # 1. Embed（检索用查询；Embedding 失败会显式抛出，不产生随机向量）
        query_embedding = await embedding_service.embed_query(search_query)
        if not query_embedding:
            logger.warning("Query embedding 为空，检索中止")
            return self._empty_result(question, search_query, rewrite, base_metadata)

        # 2. Retrieve via retriever abstraction（混合检索需要 query 文本）
        #    候选规模：开启 Reranker 时先按 Recall 取更多候选（默认 20）
        candidates_k = top_k
        if self._reranker.enabled:
            candidates_k = max(top_k, getattr(settings, "RERANKER_CANDIDATES", 20))

        raw_results = await self._retriever.retrieve(
            embedding=query_embedding,
            knowledge_base_id=knowledge_base_id,
            top_k=candidates_k,
            query=search_query,
        )
        logger.info(
            f"Retriever search: kb_id={knowledge_base_id}, candidates_k={candidates_k}, "
            f"results={len(raw_results)}"
        )

        if not raw_results:
            return self._empty_result(question, search_query, rewrite, base_metadata)

        # 3. 召回分阈值过滤（阈值作用于召回分数的既有语义保持不变）
        relevant = [r for r in raw_results if r.get("score", 0) >= min_score]

        if not relevant:
            logger.info(f"所有 {len(raw_results)} 条结果低于阈值 {min_score}，视为无结果")
            return self._empty_result(question, search_query, rewrite, base_metadata)

        # 4. Rerank（Precision；超时/异常自动回退召回顺序，永不抛异常）
        rerank_outcome = await self._reranker.rerank(
            search_query, relevant, top_k=top_k
        )
        final_chunks = rerank_outcome.results or relevant[:top_k]

        base_metadata["rerank"] = rerank_outcome.to_dict()
        base_metadata["retrieval_candidates"] = len(raw_results)
        base_metadata["after_threshold"] = len(relevant)
        base_metadata["final_context"] = len(final_chunks)

        # 5. Build citations
        citations = self._citation_builder.build(final_chunks)

        # 6. Build context & sources (backward‑compatible)
        context_parts: list[str] = []
        sources: list[dict[str, Any]] = []

        for i, r in enumerate(final_chunks):
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

        return RetrievalResult(
            results=final_chunks,
            context="\n\n".join(context_parts),
            sources=sources,
            citations=citations,
            metadata=base_metadata,
            original_query=question,
            search_query=search_query,
            rewrite_status=rewrite.rewrite_status,
            has_results=True,
        )

    def _empty_result(
        self,
        question: str,
        search_query: str,
        rewrite,
        metadata: dict[str, Any],
    ) -> RetrievalResult:
        """构造"无可用结果"的返回值，同时保留 Query Rewrite 诊断信息。"""
        return RetrievalResult(
            metadata=metadata,
            original_query=question,
            search_query=search_query,
            rewrite_status=rewrite.rewrite_status,
            has_results=False,
        )
