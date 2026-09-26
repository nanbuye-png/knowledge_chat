"""Query Rewriter 抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import QueryRewriteResult


class QueryRewriter(ABC):
    """把用户提问改写为检索查询的组件。

    实现必须遵守两条硬约束：

    1. **永不抛异常** —— 任何内部失败都要转成
       :class:`QueryRewriteResult` 并回退到原始 Query。
    2. **永不修改 original_query** —— 只提供额外的
       ``rewritten_query`` 供检索使用。
    """

    @abstractmethod
    async def rewrite(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> QueryRewriteResult:
        """Rewrite *query* into a retrieval-friendly search query.

        Args:
            query: 用户原始提问。
            history: 对话历史（``[{"role": "user", "content": "..."}]``），
                可选，用于补全指代与省略主语。

        Returns:
            一定返回 :class:`QueryRewriteResult`（失败时 ``rewrite_status``
            为 ``fallback``/``skipped``/``disabled``，且
            ``rewritten_query == original_query``）。
        """
        ...
