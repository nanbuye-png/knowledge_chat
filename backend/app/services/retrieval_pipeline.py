"""Retrieval Pipeline — decouples document retrieval from ChatService.

Provides a single entry-point for RAG retrieval steps:
1. Embed the user query
2. Search the vector store
3. Score‑filter & build context

Future extensions (hybrid search, reranker, citation) will be injected
into this pipeline without affecting ChatService.
"""
from __future__ import annotations

import time
from typing import Any

from loguru import logger

from ..services.citation.builder import CitationBuilder
from ..services.embedding_service import embedding_service
from ..services.metrics import track_rag_stage, track_retrieval_chunks
from ..core.config import settings
from ..storage.database import async_session
from .knowledge.runtime_config import KnowledgeRuntimeConfigService
from .query.factory import create_query_rewriter
from .retrieval.factory import RetrieverFactory
from .retrieval.context_filter import ContextFilter
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
        self._context_filter = ContextFilter(
            threshold=getattr(settings, "CONTEXT_SCORE_THRESHOLD", 0.0),
            score_source=getattr(settings, "CONTEXT_SCORE_SOURCE", "auto"),
        )
        # 召回分下限由配置驱动（原先硬编码 0.3，导致"决定什么进入 LLM"的阈值
        # 无法配置、也无法按检索模式标定）
        self._min_score = float(getattr(settings, "RETRIEVAL_MIN_SCORE", self._min_score))

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
        # §5.6：Query Rewrite 是 RAG 链路的第一个可变阶段，单独计时
        track_rag_stage("rewrite", rewrite.latency_ms / 1000.0)

        base_metadata = {"rewrite": rewrite.to_dict()}

        # 1. Embed（检索用查询；Embedding 失败会显式抛出，不产生随机向量）
        t_embed = time.monotonic()
        query_embedding = await embedding_service.embed_query(search_query)
        track_rag_stage("embed", time.monotonic() - t_embed)
        if not query_embedding:
            logger.warning("Query embedding 为空，检索中止")
            return self._empty_result(question, search_query, rewrite, base_metadata)

        # 2. Retrieve via retriever abstraction（混合检索需要 query 文本）
        #    候选规模：开启 Reranker 时先按 Recall 取更多候选（默认 20）
        candidates_k = top_k
        if self._reranker.enabled:
            candidates_k = max(top_k, getattr(settings, "RERANKER_CANDIDATES", 20))

        t_retrieve = time.monotonic()
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
        base_metadata["retrieval_latency_ms"] = round(
            (time.monotonic() - t_retrieve) * 1000, 1
        )
        # §5.6：召回规模进指标 —— 只监控总耗时无法判断"是不是检索变慢了"
        track_retrieval_chunks("candidates", len(raw_results))
        track_rag_stage("retrieve", time.monotonic() - t_retrieve)

        if not raw_results:
            return self._empty_result(question, search_query, rewrite, base_metadata)

        # 3. 召回分阈值过滤（阈值作用于召回分数的既有语义保持不变）
        relevant = [r for r in raw_results if r.get("score", 0) >= min_score]

        if not relevant:
            logger.info(f"所有 {len(raw_results)} 条结果低于阈值 {min_score}，视为无结果")
            return self._empty_result(question, search_query, rewrite, base_metadata)

        # 4. Rerank（Precision；超时/异常自动回退召回顺序，永不抛异常）
        t_rerank = time.monotonic()
        rerank_outcome = await self._reranker.rerank(
            search_query, relevant, top_k=top_k
        )
        track_rag_stage("rerank", time.monotonic() - t_rerank)
        final_chunks = rerank_outcome.results or relevant[:top_k]

        base_metadata["rerank"] = rerank_outcome.to_dict()
        base_metadata["retrieval_candidates"] = len(raw_results)
        base_metadata["after_threshold"] = len(relevant)
        track_retrieval_chunks("after_threshold", len(relevant))

        # 5. Context Filtering（§5.4）：低于阈值的 chunk 不进入 LLM，并记录明细
        t_filter = time.monotonic()
        filter_outcome = self._context_filter.apply(final_chunks)
        track_rag_stage("context_filter", time.monotonic() - t_filter)
        final_chunks = filter_outcome.chunks
        base_metadata["context_filter"] = filter_outcome.to_dict()
        base_metadata["final_context"] = len(final_chunks)
        track_retrieval_chunks("final_context", len(final_chunks))

        if not final_chunks:
            logger.info(
                "Context filtering 过滤掉全部候选 "
                f"(threshold={filter_outcome.threshold}, status={filter_outcome.status})"
            )
            return self._empty_result(question, search_query, rewrite, base_metadata)

        # 6. Build citations
        citations = self._citation_builder.build(final_chunks)

        # 7. Build context & sources (backward‑compatible)
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
                # §5.5：引用追溯定位信息
                "page": r.get("page"),
                "section": r.get("section"),
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
