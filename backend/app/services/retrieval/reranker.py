"""Reranker — abstract interface for post‑retrieval relevance scoring.

A reranker re‑scores the raw results returned by a :class:`BaseRetriever`
before they are passed to the prompt builder.  This allows injecting
cross‑encoder models, LLM‑based rerankers, or custom scoring logic
without touching the retriever or the vector store.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Reranker(ABC):
    """Abstract base class for reranking retrieved document chunks.

    Implementors receive the original query string and a list of raw
    result dicts, and return a (possibly re‑ordered and/or filtered)
    list with updated scores.

    Usage::

        reranker = CrossEncoderReranker(model_name="BAAI/bge-reranker-v2-m3")
        reranked = await reranker.rerank("什么是知识库？", raw_results)
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Re‑score and re‑order *results* based on relevance to *query*.

        Args:
            query: The original user query string.
            results: Raw retrieval results, each a dict with at least
                ``text`` and ``score`` keys.

        Returns:
            The reranked results list.  The order and scores may differ
            from the input.  Implementations may also filter results
            (e.g. drop those below a threshold).
        """
        ...