"""请求级指标与 request_id 中间件（Phase 3 §5.6）。

审计 §5.6 实测：``track_request`` 零调用点、``/metrics`` 未注册 → 抓取目标
永远是 down。本中间件做三件事：

1. 为每个请求分配 / 透传 ``X-Request-ID``（写入 contextvar，日志自动携带）；
2. 记录请求耗时与状态码（``track_request``）；
3. 回写 ``X-Request-ID`` / ``X-Response-Time-Ms``，方便前端与排障对照。

注意：``BaseHTTPMiddleware`` 的耗时是「拿到响应对象」的时间，对 SSE 流式接口
等价于首字节/建连耗时（而不是整个流的时长），这正是我们想要的——
流式时长由业务侧的分段耗时指标回答（见 :mod:`app.services.metrics`）。
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware

from ..core.config import settings
from ..core.context import new_request_id, set_request_id
from ..services.metrics import track_request

#: 探针 / 指标抓取本身不产生业务指标（否则会自我污染且抬高 QPS 统计）
_SKIP_PATHS = frozenset({"/metrics", "/api/health", "/"})


class MetricsMiddleware(BaseHTTPMiddleware):
    """请求级指标 + request_id 透传。"""

    async def dispatch(self, request, call_next):
        request_id = set_request_id(request.headers.get("X-Request-ID") or new_request_id())
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 异常也要计入指标与耗时，否则 5xx 在监控里不可见
            self._record(request, 500, time.perf_counter() - start)
            raise

        latency = time.perf_counter() - start
        self._record(request, response.status_code, latency)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{latency * 1000:.1f}"
        return response

    @staticmethod
    def _record(request, status: int, latency: float) -> None:
        if not getattr(settings, "METRICS_ENABLED", True):
            return

        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or request.url.path
        if endpoint in _SKIP_PATHS:
            return

        try:
            track_request(request.method, endpoint, status, latency)
        except Exception:  # pragma: no cover - 指标绝不影响主链路
            pass
