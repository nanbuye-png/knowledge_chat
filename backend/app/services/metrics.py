"""Prometheus metrics for the application."""
from fastapi import APIRouter, Response
from typing import Optional

# Lazy import - prometheus_client may not be installed in dev
_metrics_available = False
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest
    _metrics_available = True
except ImportError:
    Counter = Histogram = Gauge = generate_latest = None

router = APIRouter(tags=["监控"])


def _ensure_metrics():
    if not _metrics_available:
        raise RuntimeError("prometheus_client not installed. Run: pip install prometheus-client")


# API metrics
if _metrics_available:
    REQUEST_COUNT = Counter(
        "knowledge_request_total", "Total request count",
        ["method", "endpoint", "status"],
    )
    REQUEST_LATENCY = Histogram(
        "knowledge_request_latency_seconds", "Request latency",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
    )
    ERROR_COUNT = Counter(
        "knowledge_error_total", "Total error count",
        ["method", "endpoint", "error_type"],
    )
    LLM_TOKENS = Counter(
        "knowledge_llm_tokens_total", "LLM tokens used",
        ["model", "type"],
    )
    LLM_COST = Counter(
        "knowledge_llm_cost_total", "LLM cost in USD", ["model"],
    )
    LLM_LATENCY = Histogram(
        "knowledge_llm_latency_seconds", "LLM request latency", ["model"],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    )
    ACTIVE_USERS = Gauge("knowledge_active_users", "Currently active users")
    TOTAL_DOCUMENTS = Gauge("knowledge_documents_total", "Total documents")
    TOTAL_KNOWLEDGE_BASES = Gauge("knowledge_bases_total", "Total knowledge bases")
    TOTAL_ORGANIZATIONS = Gauge("knowledge_organizations_total", "Total organizations")
    CACHE_HITS = Counter("knowledge_cache_hits_total", "Cache hit count")
    CACHE_MISSES = Counter("knowledge_cache_misses_total", "Cache miss count")

    # ---- RAG 链路分段耗时与规模（Phase 3 §5.6）----
    # 只监控总耗时的系统回答不了「慢在哪一段」，因此按阶段拆开：
    # rewrite / embed / retrieve / rerank / context_filter / llm。
    RAG_STAGE_LATENCY = Histogram(
        "knowledge_rag_stage_latency_seconds", "RAG pipeline stage latency",
        ["stage"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    )
    RETRIEVAL_CHUNKS = Histogram(
        "knowledge_retrieval_chunks", "Retrieved chunk counts by stage",
        ["stage"],
        buckets=(0, 1, 2, 3, 5, 8, 13, 21, 34),
    )
    ABSTENTION_TOTAL = Counter(
        "knowledge_abstention_total", "Abstention decisions", ["reason"]
    )

    # ---- 韧性 / 入库可观测性（Phase 3 §5.2、§5.3）----
    RETRY_TOTAL = Counter("knowledge_retry_total", "Retry attempts", ["operation"])
    RETRY_EXHAUSTED_TOTAL = Counter(
        "knowledge_retry_exhausted_total", "Retries exhausted", ["operation"]
    )
    DOCUMENT_STATUS_TOTAL = Counter(
        "knowledge_document_status_total", "Document status transitions", ["status"]
    )
    DOCUMENT_DEDUP_TOTAL = Counter(
        "knowledge_document_dedup_total", "Duplicate upload decisions", ["result"]
    )


def track_request(method: str, endpoint: str, status: int, latency: float):
    """Track an API request."""
    _ensure_metrics()
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)
    if status >= 400:
        error_type = "client" if status < 500 else "server"
        ERROR_COUNT.labels(method=method, endpoint=endpoint, error_type=error_type).inc()


def track_llm_call(model: str, prompt_tokens: int, completion_tokens: int, latency: float):
    """Track an LLM call."""
    _ensure_metrics()
    LLM_TOKENS.labels(model=model, type="prompt").inc(prompt_tokens)
    LLM_TOKENS.labels(model=model, type="completion").inc(completion_tokens)
    LLM_LATENCY.labels(model=model).observe(latency)


# ---------------------------------------------------------------------------
# 业务 / RAG 指标（Phase 3 §5.6）
#
# 这些函数全部把「指标不可用」当作非致命情况：监控不能影响主链路，
# 未安装 prometheus_client 时静默跳过（而不是让业务请求 500）。
# ---------------------------------------------------------------------------


def track_rag_stage(stage: str, seconds: float) -> None:
    """记录某个 RAG 阶段的耗时（召回 / 重排 / 生成 …）。"""
    if not _metrics_available:
        return
    RAG_STAGE_LATENCY.labels(stage=stage).observe(max(0.0, seconds))


def track_retrieval_chunks(stage: str, count: int) -> None:
    """记录某阶段的 chunk 数量（candidates / after_threshold / final_context）。"""
    if not _metrics_available:
        return
    RETRIEVAL_CHUNKS.labels(stage=stage).observe(max(0, int(count)))


def track_abstention(reason: str) -> None:
    """记录一次拒答及其原因（no_context / low_score / low_rerank）。"""
    if not _metrics_available:
        return
    ABSTENTION_TOTAL.labels(reason=reason or "unknown").inc()


def track_retry(operation: str) -> None:
    """记录一次重试（含 operation，便于定位是哪一路在抖动）。"""
    if not _metrics_available:
        return
    RETRY_TOTAL.labels(operation=operation or "unknown").inc()


def track_retry_exhausted(operation: str) -> None:
    """记录一次「重试耗尽」——这是真正需要告警的信号。"""
    if not _metrics_available:
        return
    RETRY_EXHAUSTED_TOTAL.labels(operation=operation or "unknown").inc()


def track_document_status(status: str) -> None:
    """记录文档状态流转次数。"""
    if not _metrics_available:
        return
    DOCUMENT_STATUS_TOTAL.labels(status=status).inc()


def track_document_dedup(result: str) -> None:
    """记录上传去重决策：skipped / reused_failed / created。"""
    if not _metrics_available:
        return
    DOCUMENT_DEDUP_TOTAL.labels(result=result).inc()


def track_cache(cache: str, hit: bool) -> None:
    """记录一次缓存访问（Phase 3 §5.4：缓存必须能看出命中率）。

    Args:
        cache: 缓存名（如 ``retrieval``）。
        hit: 是否命中。
    """
    if not _metrics_available:
        return

    counter = CACHE_HITS if hit else CACHE_MISSES
    # 兼容历史定义：CACHE_HITS/MISSES 目前无 label；带 label 时按 cache 维度区分
    if getattr(counter, "_labelnames", ()):
        counter.labels(cache=cache).inc()
    else:
        counter.inc()


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    _ensure_metrics()
    return Response(content=generate_latest(), media_type="text/plain")