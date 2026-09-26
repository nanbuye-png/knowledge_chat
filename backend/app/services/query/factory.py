"""Query Rewriter 工厂 — 根据配置创建改写器。"""

from __future__ import annotations

from ...core.config import Settings, settings
from .base import QueryRewriter
from .llm_rewriter import LLMQueryRewriter, PassthroughRewriter


def create_query_rewriter(
    settings_obj: Settings | None = None,
    llm=None,
) -> QueryRewriter:
    """Create the configured :class:`QueryRewriter`.

    Args:
        settings_obj: Settings override (defaults to the global settings).
        llm: Optional pre-built LLM provider (useful for tests / reuse).

    Returns:
        :class:`PassthroughRewriter` when ``QUERY_REWRITE_ENABLED`` is off,
        otherwise :class:`LLMQueryRewriter` (which degrades to the original
        query on any failure).
    """
    conf = settings_obj or settings

    if not getattr(conf, "QUERY_REWRITE_ENABLED", True):
        return PassthroughRewriter()

    return LLMQueryRewriter(
        llm=llm,
        timeout=getattr(conf, "QUERY_REWRITE_TIMEOUT", 10.0),
        max_history=getattr(conf, "QUERY_REWRITE_MAX_HISTORY", 4),
        min_chars=getattr(conf, "QUERY_REWRITE_MIN_CHARS", 4),
        max_chars=getattr(conf, "QUERY_REWRITE_MAX_CHARS", 200),
        enabled=True,
    )
