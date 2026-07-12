"""数据库提示词 Provider — 从数据库加载提示词模板。

提供 :class:`DatabasePromptProvider`，在运行时从 ``prompt_templates`` 表
读取提示词模板。当数据库中没有匹配的模板时，回退到配置的
:class:`BasePromptProvider`（默认为 :class:`DefaultPromptProvider`）。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from .base import BasePromptProvider
from .default import DefaultPromptProvider
from ..models.prompt_template import PromptTemplate


async def _query_template(
    session: AsyncSession, prompt_type: str
) -> PromptTemplate | None:
    """查询数据库中给定类型的启用模板。

    参数：
        session: 活动的异步 SQLAlchemy 会话。
        prompt_type: 要查询的 ``prompt_type`` 值（如 ``"chat"``、``"rag"``）。

    返回值：
        按 ``id`` 升序排列的第一个匹配 :class:`PromptTemplate`，
        如果没有启用的模板则返回 ``None``。

    异常：
        SQLAlchemyError: 任何数据库错误都会传播给调用方。
    """
    stmt = (
        select(PromptTemplate)
        .where(
            PromptTemplate.prompt_type == prompt_type,
            PromptTemplate.enabled == True,  # noqa: E712
        )
        .order_by(PromptTemplate.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


class DatabasePromptProvider(BasePromptProvider):
    """从 ``prompt_templates`` 表读取模板的提示词提供者。

    每个提示词方法首先尝试从数据库加载对应模板
    （``prompt_type`` = ``"chat"`` / ``"rag"``，``enabled = True``）。
    如果找到匹配记录，则使用其 ``content``（支持可选的
    ``str.format`` 插值）。否则将请求委托给 *fallback_provider*。

    用法::

        provider = DatabasePromptProvider(session=db)
        # 或使用自定义回退：
        provider = DatabasePromptProvider(
            session=db,
            fallback_provider=CustomPromptProvider(),
        )

    参数：
        session: 用于所有数据库查询的异步 SQLAlchemy 会话。
        fallback_provider: 当数据库中不存在匹配模板时使用的
            :class:`BasePromptProvider`。默认为 :class:`DefaultPromptProvider`。
    """

    def __init__(
        self,
        session: AsyncSession,
        fallback_provider: BasePromptProvider | None = None,
    ) -> None:
        self._session = session
        self._fallback = fallback_provider or DefaultPromptProvider()
        logger.debug("DatabasePromptProvider 已初始化")

    # ------------------------------------------------------------------
    # BasePromptProvider 接口（异步变体）
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        """同步访问器 — 返回回退的系统提示词。

        DatabasePromptProvider 需要异步 I/O 来访问数据库。
        在同步上下文中，直接返回回退提供者的系统提示词。

        使用 :meth:`get_system_prompt` 进行基于数据库的解析。
        """
        return self._fallback.system_prompt

    async def get_system_prompt(self) -> str:
        """从数据库或回退解析系统提示词。

        查找 ``prompt_type == "chat"`` 且 ``enabled == True`` 的模板。

        返回值：
            匹配模板的 ``content``，或回退提供者的 ``system_prompt``。
        """
        template = await _query_template(self._session, "chat")
        if template is not None:
            logger.debug("使用数据库中的系统提示词 (id={})".format(template.id))
            return template.content
        logger.debug("未找到数据库系统提示词 — 使用回退")
        return self._fallback.system_prompt

    def build_rag_prompt(self, context: str, question: str) -> str:
        """同步 RAG 提示词 — 委托给回退提供者。

        异步上下文请使用 :meth:`get_rag_prompt`。
        """
        return self._fallback.build_rag_prompt(context, question)

    async def get_rag_prompt(self, context: str, question: str) -> str:
        """从数据库或回退构建 RAG 提示词。

        查找 ``prompt_type == "rag"`` 且 ``enabled == True`` 的模板。
        如果找到，则使用 ``str.format`` 将 ``context`` 和 ``question``
        格式化到 ``content`` 中。

        参数：
            context: 检索到的文档块。
            question: 用户的问题。

        返回值：
            格式化后的提示词字符串。
        """
        template = await _query_template(self._session, "rag")
        if template is not None:
            try:
                formatted = template.content.format(context=context, question=question)
                logger.debug("使用数据库中的 RAG 提示词 (id={})".format(template.id))
                return formatted
            except KeyError as exc:
                logger.warning(
                    "RAG 模板 content 缺少占位符: {} — 回退".format(exc)
                )
        logger.debug("未找到数据库 RAG 提示词 — 使用回退")
        return self._fallback.build_rag_prompt(context, question)

    def build_chat_prompt(self, message: str) -> str:
        """同步聊天提示词 — 委托给回退提供者。

        异步上下文请使用 :meth:`get_chat_prompt`。
        """
        return self._fallback.build_chat_prompt(message)

    async def get_chat_prompt(self, message: str) -> str:
        """从数据库或回退构建聊天提示词。

        查找 ``prompt_type == "chat"`` 且 ``enabled == True`` 的模板。
        如果找到，则使用 ``str.format`` 将 ``message`` 格式化到
        ``content`` 中。

        参数：
            message: 用户的聊天消息。

        返回值：
            格式化后的提示词字符串。
        """
        template = await _query_template(self._session, "chat")
        if template is not None:
            try:
                formatted = template.content.format(message=message)
                logger.debug("使用数据库中的聊天提示词 (id={})".format(template.id))
                return formatted
            except KeyError as exc:
                logger.warning(
                    "聊天模板 content 缺少占位符: {} — 回退".format(exc)
                )
        logger.debug("未找到数据库聊天提示词 — 使用回退")
        return self._fallback.build_chat_prompt(message)