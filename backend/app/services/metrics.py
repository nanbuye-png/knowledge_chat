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


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    _ensure_metrics()
    return Response(content=generate_latest(), media_type="text/plain")