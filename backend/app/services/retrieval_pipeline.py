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
from ..storage.database import async_session
from .knowledge.runtime_config import KnowledgeRuntimeConfigService
from .retrieval.factory import RetrieverFactory
from .retrieval.models import RetrievalResult

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        question: str,
        knowledge_base_id: int,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> RetrievalResult:
        """Run the full retrieval pipeline for a single query.

        Steps:
            1. Embed *question* via :func:`embedding_service.embed_query`.
            2. Delegate to :class:`BaseRetriever` for vector search.
            3. Score‑filter results.
            4. Build concatenated context + source list.

        Args:
            question: The user's natural‑language question.
            knowledge_base_id: Restrict search to this knowledge base.
            top_k: Override default retrieval count (default 5).
            min_score: Override default score threshold (default 0.3).

        Returns:
            A :class:`RetrievalResult` containing results, context, sources,
            and a convenience :attr:`~RetrievalResult.has_results` flag.
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

        # 1. Embed
        query_embedding = await embedding_service.embed_query(question)
        if not query_embedding:
            return RetrievalResult()

        # 2. Retrieve via retriever abstraction
        raw_results = await self._retriever.retrieve(
            embedding=query_embedding,
            knowledge_base_id=knowledge_base_id,
            top_k=top_k,
        )
        logger.info(
            f"Retriever search: kb_id={knowledge_base_id}, top_k={top_k}, "
            f"results={len(raw_results)}"
        )

        if not raw_results:
            return RetrievalResult()

        # 3. Score‑filter
        relevant = [r for r in raw_results if r.get("score", 0) >= min_score]

        if not relevant:
            return RetrievalResult()

        # 4. Build citations
        citations = self._citation_builder.build(relevant)

        # 5. Build context & sources (backward‑compatible)
        context_parts: list[str] = []
        sources: list[dict[str, Any]] = []

        for i, r in enumerate(relevant):
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
            results=relevant,
            context="\n\n".join(context_parts),
            sources=sources,
            citations=citations,
            has_results=True,
        )
