"""Reranker — abstract interface for post‑retrieval relevance scoring.

A reranker re‑scores the raw results returned by a :class:`BaseRetriever`
before they are passed to the prompt builder.  This allows injecting
cross‑encoder models, LLM‑based rerankers, or custom scoring logic
without touching the retriever or the vector store.
"""

from __future__ import annotations

import asyncio
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from loguru import logger

from .tokenizer import tokenize


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


# ===========================================================================
# Reranker 实现（Phase 1 §5.3）
# ===========================================================================


class RerankerError(RuntimeError):
    """重排模型加载/推理失败。

    调用方（:class:`RerankerService`）必须捕获它并回退到融合排序，
    绝不允许重排异常导致整个问答不可用。
    """


class RerankStatus(str, Enum):
    """重排终态。"""

    RERANKED = "reranked"  # 重排成功
    FALLBACK = "fallback"  # 重排失败，已回退到召回顺序
    DISABLED = "disabled"  # 功能关闭
    SKIPPED = "skipped"  # 无候选，直接跳过


@dataclass
class RerankOutcome:
    """重排结果 + 可观测指标。

    Attributes:
        results: 重排（并截断到 ``top_k``）后的结果列表。
        candidates_in: 送进重排的候选数（retrieval_candidates）。
        candidates_out: 重排后的结果数（reranked_candidates）。
        latency_ms: 重排耗时（reranker_latency）。
        status: 见 :class:`RerankStatus`。
        reranker: 使用的重排器名称（lexical / cross_encoder / passthrough）。
        error: 失败原因（诊断用）。
    """

    results: list[dict[str, Any]] = field(default_factory=list)
    candidates_in: int = 0
    candidates_out: int = 0
    latency_ms: float = 0.0
    status: str = RerankStatus.DISABLED.value
    reranker: str = "none"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reranker": self.reranker,
            "candidates_in": self.candidates_in,
            "candidates_out": self.candidates_out,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
        }


class PassthroughReranker(Reranker):
    """不重排（关闭时使用），保持召回顺序。"""

    async def rerank(
        self, query: str, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return list(results)


class LexicalOverlapReranker(Reranker):
    """零依赖的词项重叠重排器（默认实现）。

    用与稀疏索引相同的分词器（中文 bi-gram + 拉丁词）计算
    ``|query ∩ chunk| / |query|`` 作为相关性分数（∈ [0,1]）。

    它是"可用的重排"但不是 cross-encoder：优点是零模型下载、确定性强、
    可在 CI 中稳定运行；需要更高精度时把 ``RERANKER_TYPE`` 切到
    ``cross_encoder``。它的分数天然落在 [0,1]，因此可以直接用于
    §5.4 的阈值过滤与 §5.6 的拒答判断。
    """

    name = "lexical"

    async def rerank(
        self, query: str, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        query_terms = set(tokenize(query))
        if not query_terms:
            return list(results)

        reranked: list[dict[str, Any]] = []
        for result in results:
            chunk_terms = set(tokenize(result.get("text", "")))
            overlap = len(query_terms & chunk_terms)
            item = dict(result)
            item["rerank_score"] = round(overlap / len(query_terms), 6)
            reranked.append(item)

        # 稳定排序：分数相同保持召回顺序
        reranked.sort(key=lambda r: r["rerank_score"], reverse=True)
        return reranked


#: CrossEncoder 实例缓存：model_name → 模型
_CROSS_ENCODER_CACHE: dict[str, Any] = {}


def _load_cross_encoder(model_name: str) -> Any:
    """Load (and cache) a sentence-transformers ``CrossEncoder``.

    Raises:
        RerankerError: 依赖缺失或模型加载失败。
    """
    cached = _CROSS_ENCODER_CACHE.get(model_name)
    if cached is not None:
        return cached

    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RerankerError(
            "sentence-transformers 未安装，无法使用 cross-encoder 重排。"
            "请执行: pip install sentence-transformers"
        ) from exc

    try:
        logger.info(f"Loading reranker model: {model_name}")
        model = CrossEncoder(model_name)
    except Exception as exc:
        raise RerankerError(f"加载重排模型失败（{model_name}）: {exc}") from exc

    _CROSS_ENCODER_CACHE[model_name] = model
    logger.info(f"✅ Reranker model loaded: {model_name}")
    return model


class CrossEncoderReranker(Reranker):
    """Cross-encoder 重排器（精度最高，需要本地模型）。

    分数经 ``sigmoid`` 映射到 (0,1)，与词项重叠分数同区间，
    便于统一阈值化。
    """

    name = "cross_encoder"

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
        batch_size: int = 16,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size

    async def rerank(
        self, query: str, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not results:
            return []

        model = await asyncio.to_thread(_load_cross_encoder, self.model_name)
        pairs = [(query, r.get("text", "")) for r in results]

        try:
            raw_scores = await asyncio.to_thread(
                lambda: model.predict(pairs, batch_size=self.batch_size)
            )
        except Exception as exc:
            raise RerankerError(f"重排推理失败: {exc}") from exc

        reranked: list[dict[str, Any]] = []
        for result, raw in zip(results, raw_scores):
            item = dict(result)
            item["rerank_raw_score"] = float(raw)
            item["rerank_score"] = round(_sigmoid(float(raw)), 6)
            reranked.append(item)

        reranked.sort(key=lambda r: r["rerank_score"], reverse=True)
        return reranked


def _sigmoid(value: float) -> float:
    """把 cross-encoder 的原始 logit 映射到 (0, 1)。"""
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


# ===========================================================================
# 编排：超时 / 降级 / 指标
# ===========================================================================


class RerankerService:
    """带超时、降级与指标记录的重排编排（Phase 1 §5.3）。

    约束（对应计划 §5.3）：
    * Retriever 负责 Recall，Reranker 负责 Precision；
    * ``top_k`` 可配置；
    * 超时 / 异常 / 输出为空 → 回退召回顺序（``status=fallback``）；
    * **绝不抛异常**给问答链路。
    """

    def __init__(
        self,
        reranker: Optional[Reranker] = None,
        *,
        enabled: bool = True,
        top_k: int = 5,
        timeout: float = 10.0,
        name: str = "passthrough",
    ) -> None:
        self._reranker = reranker or PassthroughReranker()
        self._enabled = enabled
        self._top_k = max(int(top_k), 1)
        self._timeout = timeout
        self._name = getattr(self._reranker, "name", name)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def name(self) -> str:
        return self._name

    async def rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> RerankOutcome:
        """Rerank *results* against *query*, always returning an outcome."""
        limit = max(int(top_k) if top_k else self._top_k, 1)
        start = time.monotonic()
        candidates = list(results or [])

        if not candidates:
            return self._outcome([], 0, RerankStatus.SKIPPED, start)

        if not self._enabled:
            return self._outcome(
                candidates[:limit], len(candidates), RerankStatus.DISABLED, start
            )

        if not query or not query.strip():
            return self._outcome(
                candidates[:limit],
                len(candidates),
                RerankStatus.FALLBACK,
                start,
                error="空查询",
            )

        try:
            reranked = await asyncio.wait_for(
                self._reranker.rerank(query, candidates), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Reranker 超时（>{self._timeout}s，{self._name}），回退召回顺序"
            )
            return self._outcome(
                candidates[:limit],
                len(candidates),
                RerankStatus.FALLBACK,
                start,
                error="timeout",
            )
        except Exception as exc:  # noqa: BLE001 - 重排失败必须可降级
            logger.warning(
                f"Reranker 失败（{self._name}: {type(exc).__name__}: {exc}），"
                f"回退召回顺序"
            )
            return self._outcome(
                candidates[:limit],
                len(candidates),
                RerankStatus.FALLBACK,
                start,
                error=f"{type(exc).__name__}: {exc}",
            )

        if not reranked:
            return self._outcome(
                candidates[:limit],
                len(candidates),
                RerankStatus.FALLBACK,
                start,
                error="重排返回空结果",
            )

        outcome = self._outcome(
            list(reranked)[:limit], len(candidates), RerankStatus.RERANKED, start
        )
        logger.info(
            f"Rerank({self._name}): candidates={outcome.candidates_in} → "
            f"{outcome.candidates_out}, latency={outcome.latency_ms:.0f}ms"
        )
        return outcome

    def _outcome(
        self,
        results: list[dict[str, Any]],
        candidates_in: int,
        status: RerankStatus,
        start: float,
        error: str = "",
    ) -> RerankOutcome:
        return RerankOutcome(
            results=results,
            candidates_in=candidates_in,
            candidates_out=len(results),
            latency_ms=(time.monotonic() - start) * 1000,
            status=status.value,
            reranker=self._name,
            error=error,
        )


def create_reranker_service(settings_obj=None) -> RerankerService:
    """Create the configured :class:`RerankerService`.

    ``RERANKER_ENABLED=false`` → 纯透传（不重排）。
    ``RERANKER_TYPE=lexical``（默认）→ 零依赖词项重叠重排。
    ``RERANKER_TYPE=cross_encoder`` → 本地 cross-encoder（需模型）。
    """
    from ...core.config import settings

    conf = settings_obj or settings
    top_k = getattr(conf, "RERANKER_TOP_K", 5)
    timeout = getattr(conf, "RERANKER_TIMEOUT", 10.0)

    if not getattr(conf, "RERANKER_ENABLED", True):
        return RerankerService(
            PassthroughReranker(), enabled=False, top_k=top_k, name="passthrough"
        )

    reranker_type = (getattr(conf, "RERANKER_TYPE", "lexical") or "lexical").lower()
    if reranker_type == "cross_encoder":
        instance: Reranker = CrossEncoderReranker(
            model_name=getattr(conf, "RERANKER_MODEL", "BAAI/bge-reranker-base"),
            batch_size=getattr(conf, "RERANKER_BATCH_SIZE", 16),
        )
    else:
        instance = LexicalOverlapReranker()

    return RerankerService(instance, enabled=True, top_k=top_k, timeout=timeout)

