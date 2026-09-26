"""Query Rewrite — 把用户提问改写为更适合检索的查询（Phase 1 §5.1）。

设计要点
--------
* 原始 Query 始终保留（``original_query``），只额外产出 ``rewritten_query``
  供检索使用，绝不修改或替换用户原问题。
* 任何失败（禁用 / 跳过 / 超时 / 异常 / 输出非法）都回退到原始 Query，
  ``rewrite_status`` 记录原因，**绝不因为改写失败而让问答失败**。
* 结构化结果 :class:`QueryRewriteResult` 便于排查与后续评测。

Usage::

    from app.services.query import create_query_rewriter

    rewriter = create_query_rewriter()
    result = await rewriter.rewrite("它多少钱？", history=[...])
    search_query = result.rewritten_query or result.original_query
"""

from .base import QueryRewriter
from .factory import create_query_rewriter
from .llm_rewriter import LLMQueryRewriter, PassthroughRewriter
from .models import QueryRewriteResult, RewriteStatus

__all__ = [
    "QueryRewriter",
    "QueryRewriteResult",
    "RewriteStatus",
    "LLMQueryRewriter",
    "PassthroughRewriter",
    "create_query_rewriter",
]
