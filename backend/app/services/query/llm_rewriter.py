"""LLM-based Query Rewriter — 带完整 fallback 的改写实现。

改写规则（Prompt 契约）
-----------------------
1. 保留原问题全部关键实体与数字，不改变用户意图；
2. 用对话历史补全指代（「它」「这个」）与省略的主语；
3. 不回答问题、不解释、不编造原文没有的信息；
4. 只输出一行改写后的查询文本（无引号、无前缀）。

失败处理
--------
超时 / 异常 / 空输出 / 超长输出 等一切异常情况统一落到 ``FALLBACK``，
并把原因写入 ``error`` 与日志 —— 调用方永远拿到可用的
``rewritten_query``（回退为原始 Query），问答链路不会中断。
"""

from __future__ import annotations

import asyncio
import re
import time

from loguru import logger

from ..llm.base import LLMProvider
from .base import QueryRewriter
from .models import QueryRewriteResult, RewriteStatus

#: 内部系统提示词（输出必须是机器可解析的一行文本，故不做成用户可编辑模板）
REWRITE_SYSTEM_PROMPT = (
    "你是检索查询重写器。请把用户的提问改写成更适合向量检索与关键词检索的独立查询。\n"
    "要求：\n"
    "1. 保留原问题中的全部关键实体、专有名词与数字，不要改变用户意图；\n"
    "2. 结合对话历史补全指代（如「它」「这个」）与被省略的主语；\n"
    "3. 不要回答问题，不要解释，不要添加原文没有的信息；\n"
    "4. 只输出一行重写后的查询文本，不要引号、不要序号、不要任何前缀说明。"
)

#: 需要从模型输出中剥掉的前缀（模型偶发不遵守格式时兜底）
_PREFIX_PATTERN = re.compile(
    r"^\s*(重写后的查询|改写后的查询|检索查询|查询|search\s*query|query)\s*[:：]\s*",
    re.IGNORECASE,
)


class PassthroughRewriter(QueryRewriter):
    """不改写（功能关闭时使用）。"""

    def __init__(self, status: str = RewriteStatus.DISABLED.value) -> None:
        self._status = status

    async def rewrite(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> QueryRewriteResult:
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=query,
            rewrite_status=self._status,
        )


class LLMQueryRewriter(QueryRewriter):
    """用 LLM 改写查询，失败时安全回退。

    Args:
        llm: :class:`LLMProvider` 实例（可注入以便测试）。
        timeout: 单次改写超时（秒）。
        max_history: 参与改写的最近消息条数。
        min_chars: 短于该长度的查询直接跳过。
        max_chars: 允许的改写结果最大长度。
        enabled: ``False`` 时等价于 :class:`PassthroughRewriter`。
    """

    def __init__(
        self,
        llm: LLMProvider | None = None,
        *,
        timeout: float = 10.0,
        max_history: int = 4,
        min_chars: int = 4,
        max_chars: int = 200,
        enabled: bool = True,
    ) -> None:
        self._llm = llm
        self._timeout = timeout
        self._max_history = max_history
        self._min_chars = min_chars
        self._max_chars = max_chars
        self._enabled = enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rewrite(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> QueryRewriteResult:
        start = time.monotonic()

        if not self._enabled:
            return self._result(query, query, RewriteStatus.DISABLED, start)

        if not query or not query.strip():
            return self._result(
                query, query, RewriteStatus.SKIPPED, start, error="查询为空"
            )

        if len(query.strip()) < self._min_chars:
            return self._result(
                query,
                query,
                RewriteStatus.SKIPPED,
                start,
                error=f"查询过短（< {self._min_chars} 字符）",
            )

        context = self._format_context(history)
        messages = [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_prompt(query, context)},
        ]

        try:
            raw = await asyncio.wait_for(self._chat(messages), timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Query rewrite 超时（>{self._timeout}s），回退原始 Query：'{query[:40]}'"
            )
            return self._result(
                query, query, RewriteStatus.FALLBACK, start,
                error="timeout", context=context,
            )
        except Exception as exc:  # noqa: BLE001 - 任何失败都必须回退，不能中断问答
            logger.warning(
                f"Query rewrite 失败（{type(exc).__name__}: {exc}），"
                f"回退原始 Query：'{query[:40]}'"
            )
            return self._result(
                query, query, RewriteStatus.FALLBACK, start,
                error=f"{type(exc).__name__}: {exc}", context=context,
            )

        rewritten = self._normalize(raw)
        invalid_reason = self._validate(rewritten)
        if invalid_reason:
            logger.warning(
                f"Query rewrite 输出非法（{invalid_reason}），回退原始 Query；"
                f"原始输出={raw!r}"
            )
            return self._result(
                query, query, RewriteStatus.FALLBACK, start,
                error=invalid_reason, context=context,
            )

        result = self._result(
            query, rewritten, RewriteStatus.REWRITTEN, start, context=context
        )
        logger.info(
            f"Query rewrite 成功: '{query[:40]}' → '{rewritten[:40]}' "
            f"（{result.latency_ms:.0f}ms）"
        )
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _chat(self, messages: list[dict]) -> str:
        if self._llm is None:
            from ...core.config import settings
            from ..llm.factory import LLMProviderFactory

            self._llm = LLMProviderFactory.create(settings)

        response = await self._llm.chat(
            messages=messages,
            stream=False,
            temperature=0.0,
            max_tokens=128,
        )
        return response if isinstance(response, str) else ""

    def _format_context(self, history: list[dict] | None) -> str:
        if not history:
            return ""
        recent = history[-self._max_history :] if self._max_history > 0 else []
        lines = []
        for item in recent:
            role = item.get("role", "user")
            content = (item.get("content") or "").strip().replace("\n", " ")
            if content:
                lines.append(f"{role}: {content[:200]}")
        return "\n".join(lines)

    @staticmethod
    def _build_user_prompt(query: str, context: str) -> str:
        if context:
            return (
                f"【对话历史】\n{context}\n\n"
                f"【当前问题】\n{query}\n\n"
                f"【重写后的查询】"
            )
        return f"【当前问题】\n{query}\n\n【重写后的查询】"

    def _normalize(self, raw: str) -> str:
        """把模型输出规整成单行查询文本。"""
        text = (raw or "").strip()
        if not text:
            return ""

        # 只取第一行有效内容（模型偶尔会多输出一行解释）
        text = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")

        # 去掉模型自加的前缀与包裹引号/反引号
        text = _PREFIX_PATTERN.sub("", text)
        text = text.strip().strip("\"'“”‘’`")
        return " ".join(text.split())

    def _validate(self, rewritten: str) -> str:
        """返回空串表示合法，否则返回非法原因。"""
        if not rewritten:
            return "空输出"
        if len(rewritten) > self._max_chars:
            return f"输出过长（{len(rewritten)} > {self._max_chars}）"
        if len(rewritten) < 2:
            return "输出过短"
        return ""

    @staticmethod
    def _result(
        original: str,
        rewritten: str,
        status: RewriteStatus,
        start: float,
        error: str = "",
        context: str = "",
    ) -> QueryRewriteResult:
        return QueryRewriteResult(
            original_query=original,
            rewritten_query=rewritten or original,
            conversation_context=context,
            rewrite_status=status.value,
            error=error,
            latency_ms=(time.monotonic() - start) * 1000,
        )
