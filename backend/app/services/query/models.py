"""Query Rewrite data model — 结构化记录改写结果与状态。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RewriteStatus(str, Enum):
    """Query Rewrite 的终态。

    * ``REWRITTEN`` — LLM 成功改写，``rewritten_query`` 可用于检索
    * ``FALLBACK``  — 改写失败（超时 / 异常 / 输出非法），已回退原始 Query
    * ``SKIPPED``   — 未调用 LLM（查询过短 / 信息不足）
    * ``DISABLED``  — 功能被配置关闭
    """

    REWRITTEN = "rewritten"
    FALLBACK = "fallback"
    SKIPPED = "skipped"
    DISABLED = "disabled"


@dataclass
class QueryRewriteResult:
    """Query Rewrite 的输出。

    Attributes:
        original_query: 用户原始提问（**永不被覆盖**）。
        rewritten_query: 用于检索的查询；回退时等于 ``original_query``。
        conversation_context: 参与改写的最近对话上下文（已裁剪，便于 Debug）。
        rewrite_status: 见 :class:`RewriteStatus`。
        error: 失败原因（诊断用；成功时为空串）。
        latency_ms: 改写耗时（毫秒）。
    """

    original_query: str
    rewritten_query: str
    conversation_context: str = ""
    rewrite_status: str = RewriteStatus.DISABLED.value
    error: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_rewrite(self) -> bool:
        """``True`` 表示确实产生了与原文不同的可用检索查询。"""
        return (
            self.rewrite_status == RewriteStatus.REWRITTEN.value
            and bool(self.rewritten_query.strip())
            and self.rewritten_query.strip() != self.original_query.strip()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "conversation_context": self.conversation_context,
            "rewrite_status": self.rewrite_status,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 2),
        }
