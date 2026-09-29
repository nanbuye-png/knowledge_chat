"""请求级上下文（Phase 3 §5.6 Observability）。

没有请求标识时，一条报错日志无法与具体请求对应；多实例 / 后台任务并发时
更无法定位。审计 §5.6 要求把「request_id / trace_id + 分段耗时」落地。

实现：``contextvars.ContextVar`` —— 中间件写入、日志 patcher 读取，
因此同一次请求内所有日志（包括 await 出去的 service / 后台任务）自动带上
同一个 request_id，且天然与并发隔离（无需 threading.local 那种坑）。
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

#: 无请求上下文时（如启动阶段、后台线程）使用的占位值
DEFAULT_REQUEST_ID = "-"

request_id_ctx: ContextVar[str] = ContextVar("request_id", default=DEFAULT_REQUEST_ID)


def new_request_id() -> str:
    """生成短 request_id（16 位十六进制）。"""
    return uuid.uuid4().hex[:16]


def set_request_id(value: str | None) -> str:
    """写入当前上下文的 request_id 并返回生效值。"""
    effective = (value or "").strip() or DEFAULT_REQUEST_ID
    request_id_ctx.set(effective)
    return effective


def get_request_id() -> str:
    """读取当前上下文的 request_id（无则返回 ``-``）。"""
    return request_id_ctx.get()
