"""kb_search 工具 —— 在指定知识库内做真实检索（审计 §4「一个真实场景」之一）。

复用生产检索链路 :class:`~app.services.retrieval_pipeline.RetrievalPipeline`
（Query Rewrite → Hybrid/Vector 检索 → Rerank → Citation），**不新建**第二条
检索实现；工具只做三件事：

1. **归属校验**（审计 §6.2）：任何检索路径都必须先确认知识库属于当前用户，
   工具端点同样不能例外，否则 `/api/tools/kb_search` 会成为绕过
   ``/api/knowledge/query`` 校验的越权读入口；
2. **输出裁剪**：片段数受 ``top_k``（上限 ``settings.TOOL_KB_SEARCH_MAX_TOP_K``）
   约束、正文按 ``settings.TOOL_KB_SEARCH_SNIPPET_CHARS`` 截断 —— 工具输出是
   给调用方（前端/未来的 LLM planner）消费的，不能把整库内容塞进一次响应；
3. **失败处理**：检索链路的原始异常只落日志（``logger.exception``，带堆栈），
   对外统一 :class:`ToolExecutionError`（固定文案，不泄漏内部细节，审计 §5.5）。
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select

from ...core.config import settings
from ...models.knowledge_base import KnowledgeBase
from .base import (
    BaseTool,
    ToolContext,
    ToolExecutionError,
    ToolPermissionDenied,
)

# 懒加载单例：import 时不构造 RetrieverFactory / 不加载模型，
# 首次调用才初始化（与 chat_service 各自持有一个实例的现状保持一致）。
_pipeline_singleton = None


def _get_pipeline():
    global _pipeline_singleton
    if _pipeline_singleton is None:
        from ..retrieval_pipeline import RetrievalPipeline

        _pipeline_singleton = RetrievalPipeline()
    return _pipeline_singleton


class KnowledgeBaseSearchTool(BaseTool):
    """知识库混合检索工具。"""

    name = "kb_search"
    description = (
        "在指定知识库内检索与问题最相关的文档片段，返回片段正文、相似度与引用信息。"
        "知识库必须是当前用户自己的知识库。"
    )

    def __init__(self, pipeline: Any = None) -> None:
        """``pipeline`` 用于注入检索链路（测试替身）；缺省走生产单例。"""
        self._pipeline = pipeline

    @property
    def parameters(self) -> dict[str, dict[str, Any]]:  # type: ignore[override]
        return {
            "query": {
                "type": "string",
                "required": True,
                "description": "检索问题（自然语言）",
                "maxLength": 500,
            },
            "knowledge_base_id": {
                "type": "integer",
                "required": True,
                "description": "知识库 ID",
                "minimum": 1,
            },
            "top_k": {
                "type": "integer",
                "description": "返回片段数量",
                "default": 5,
                "minimum": 1,
                "maximum": settings.TOOL_KB_SEARCH_MAX_TOP_K,
            },
        }

    def pipeline(self):
        return self._pipeline or _get_pipeline()

    async def run(
        self,
        context: ToolContext,
        query: str = "",
        knowledge_base_id: int = 0,
        top_k: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        if context.user is None:
            raise ToolPermissionDenied("kb_search 需要登录用户上下文")
        if context.db is None:
            raise ToolExecutionError("kb_search 缺少执行上下文（数据库会话）")

        # 1. 归属校验 —— 与 /api/knowledge/query 的前置校验同一条规则
        result = await context.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.user_id == context.user.id,
            )
        )
        kb = result.scalar_one_or_none()
        if kb is None:
            logger.warning(
                f"kb_search 拒绝访问: user_id={context.user.id} "
                f"knowledge_base_id={knowledge_base_id}"
            )
            raise ToolPermissionDenied("知识库不存在或无权访问")

        top_k = top_k or 5
        # 2. 检索（复用生产链路）
        try:
            retrieval = await self.pipeline().retrieve(
                query, knowledge_base_id, top_k=top_k
            )
        except Exception:
            logger.exception(
                f"kb_search 检索失败: knowledge_base_id={knowledge_base_id}"
            )
            raise ToolExecutionError("知识库检索失败，请稍后重试")

        snippet_chars = settings.TOOL_KB_SEARCH_SNIPPET_CHARS
        raw_sources = list(getattr(retrieval, "sources", None) or [])
        if not raw_sources:
            raw_sources = list(getattr(retrieval, "results", None) or [])

        snippets = [
            _build_snippet(index, source, snippet_chars)
            for index, source in enumerate(raw_sources[:top_k], start=1)
        ]

        return {
            "knowledge_base_id": knowledge_base_id,
            "knowledge_base_name": getattr(kb, "name", ""),
            "query": query,
            "search_query": getattr(retrieval, "search_query", "") or query,
            "rewrite_status": getattr(retrieval, "rewrite_status", ""),
            "has_results": bool(getattr(retrieval, "has_results", bool(snippets))),
            "snippet_count": len(snippets),
            "snippets": snippets,
            "citations": [
                c.to_dict() if hasattr(c, "to_dict") else c
                for c in (getattr(retrieval, "citations", None) or [])
            ],
        }


def _build_snippet(index: int, source: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """把检索层的 chunk dict 裁剪成前端/LLM 友好的片段结构。"""
    if not isinstance(source, dict):
        source = {"text": str(source)}
    content = source.get("content") or source.get("text") or ""
    content = str(content)
    snippet: dict[str, Any] = {
        "index": index,
        "document_id": source.get("document_id", ""),
        "document_name": source.get("filename") or source.get("document_name") or "",
        "score": source.get("score", 0.0),
    }
    for optional in ("page", "section", "chunk_index"):
        if source.get(optional) is not None:
            snippet[optional] = source[optional]
    snippet["content"] = content[:max_chars]
    snippet["truncated"] = len(content) > max_chars
    return snippet
