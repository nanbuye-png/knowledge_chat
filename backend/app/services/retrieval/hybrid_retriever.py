"""Hybrid Retriever — 向量召回 + BM25 稀疏召回的可配置加权融合。

```text
                 ┌── Vector Retrieval (语义)
User Query ──────┤
                 └── BM25 / Sparse Retrieval (关键词)
                         ↓
                  Weighted Fusion
                         ↓
                     Top-K Recall
```

设计要点（Phase 1 §5.2）
-----------------------
* **保留现有向量检索**：向量通道就是 :class:`VectorRetriever`，未被替换。
* **权重可配置**：``HYBRID_VECTOR_WEIGHT`` / ``HYBRID_BM25_WEIGHT``。
* **融合简单可解释**：每条通道的分数先 min-max 归一化到 [0,1]，再按权重
  加权求和；不做 RRF/学习式排序等过度设计。
* **失败可降级**：稀疏索引不可用或抛错时，按 ``SPARSE_INDEX_FALLBACK``
  退回纯向量结果，绝不让整条问答链路挂掉。
* **两条通道可独立测试**：``vector_leg`` / ``sparse_leg`` 可单独调用。
"""

from __future__ import annotations

from typing import Any, Optional

from loguru import logger

from .base import BaseRetriever
from .sparse_index import SparseIndex, get_sparse_index
from .vector_retriever import VectorRetriever


def _result_key(result: dict[str, Any]) -> str:
    """融合时用于识别"同一个 chunk"的键。"""
    return str(
        result.get("id")
        or f"{result.get('document_id', '')}_{result.get('chunk_index', '')}"
    )


def _normalize(results: list[dict[str, Any]]) -> dict[str, tuple[float, dict]]:
    """Min-max 归一化单条通道的打分到 [0, 1]。"""
    if not results:
        return {}

    scores = [float(r.get("score", 0.0)) for r in results]
    low, high = min(scores), max(scores)

    normalized: dict[str, tuple[float, dict]] = {}
    for result in results:
        score = float(result.get("score", 0.0))
        norm = 1.0 if high == low else (score - low) / (high - low)
        normalized[_result_key(result)] = (norm, result)
    return normalized


def weighted_fusion(
    vector_results: list[dict[str, Any]],
    sparse_results: list[dict[str, Any]],
    vector_weight: float,
    bm25_weight: float,
    top_k: int,
) -> list[dict[str, Any]]:
    """加权融合两条召回通道。

    ``final_score = vector_weight * normalized_vector + bm25_weight * normalized_bm25``

    返回结果保留两通道归一化分（``vector_score`` / ``bm25_score``）便于
    Debug 与评测归因。
    """
    fused: dict[str, dict[str, Any]] = {}

    for key, (norm, result) in _normalize(vector_results).items():
        fused[key] = {
            "result": dict(result),
            "score": vector_weight * norm,
            "vector_score": norm,
            "bm25_score": 0.0,
        }

    for key, (norm, result) in _normalize(sparse_results).items():
        if key in fused:
            fused[key]["score"] += bm25_weight * norm
            fused[key]["bm25_score"] = norm
        else:
            fused[key] = {
                "result": dict(result),
                "score": bm25_weight * norm,
                "vector_score": 0.0,
                "bm25_score": norm,
            }

    ordered = sorted(fused.values(), key=lambda item: item["score"], reverse=True)

    output: list[dict[str, Any]] = []
    for item in ordered[:top_k]:
        merged = item["result"]
        merged["score"] = round(item["score"], 6)
        merged["vector_score"] = round(item["vector_score"], 6)
        merged["bm25_score"] = round(item["bm25_score"], 6)
        output.append(merged)
    return output


class HybridRetriever(BaseRetriever):
    """向量 + BM25 融合检索器。

    Args:
        vector_retriever: 向量通道（默认 :class:`VectorRetriever`）。
        sparse_index: 稀疏通道（默认进程内单例）。
        vector_weight: 向量通道权重。
        bm25_weight: BM25 通道权重。
        recall_k: 每条通道的候选数（Recall 阶段）。
        sparse_fallback: 稀疏通道失败时是否退回纯向量（默认 True）。
    """

    def __init__(
        self,
        vector_retriever: Optional[BaseRetriever] = None,
        sparse_index: Optional[SparseIndex] = None,
        *,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
        recall_k: int = 20,
        sparse_fallback: bool = True,
    ) -> None:
        self._vector = vector_retriever or VectorRetriever()
        self._sparse = sparse_index
        self._vector_weight = vector_weight
        self._bm25_weight = bm25_weight
        self._recall_k = max(recall_k, 1)
        self._sparse_fallback = sparse_fallback

    # ------------------------------------------------------------------
    # Individual legs (independently testable)
    # ------------------------------------------------------------------

    async def vector_leg(
        self,
        embedding: list[float],
        knowledge_base_id: int,
        top_k: int,
    ) -> list[dict]:
        """向量通道（语义召回）。"""
        return await self._vector.retrieve(
            embedding=embedding,
            knowledge_base_id=knowledge_base_id,
            top_k=top_k,
        )

    def get_sparse_index(self) -> SparseIndex:
        if self._sparse is None:
            self._sparse = get_sparse_index()
        return self._sparse

    async def sparse_leg(
        self,
        query: str,
        knowledge_base_id: int,
        top_k: int,
    ) -> list[dict]:
        """BM25 稀疏通道（关键词召回）。"""
        index = self.get_sparse_index()
        await index.initialize()
        return await index.search(
            query=query,
            knowledge_base_id=knowledge_base_id,
            top_k=top_k,
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        embedding: list[float],
        knowledge_base_id: int,
        top_k: int = 5,
        query: str | None = None,
    ) -> list[dict]:
        """融合检索：两条通道各取 recall_k，融合后返回 top_k。"""
        recall_k = max(self._recall_k, top_k)

        vector_results = await self.vector_leg(embedding, knowledge_base_id, recall_k)

        sparse_results: list[dict] = []
        if query and query.strip():
            try:
                sparse_results = await self.sparse_leg(
                    query, knowledge_base_id, recall_k
                )
            except Exception as exc:  # noqa: BLE001 - 稀疏通道不得拖垮检索
                logger.error(f"稀疏检索失败: {exc}")
                if not self._sparse_fallback:
                    raise
                sparse_results = []

        fused = weighted_fusion(
            vector_results,
            sparse_results,
            self._vector_weight,
            self._bm25_weight,
            top_k,
        )
        logger.info(
            f"Hybrid retrieval: kb={knowledge_base_id}, "
            f"vector={len(vector_results)}, sparse={len(sparse_results)}, "
            f"fused={len(fused)} "
            f"(weights: vector={self._vector_weight}, bm25={self._bm25_weight})"
        )
        return fused
