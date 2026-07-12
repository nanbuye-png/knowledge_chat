"""提示词 Provider 解析器 — 运行时选择提示词提供者。

提供 :func:`resolve_prompt_provider`，用于创建基于给定异步会话的
:class:`DatabasePromptProvider`。返回的提供者首先尝试从数据库加载模板，
当没有匹配模板时回退到默认提供者。
"""
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BasePromptProvider
from .factory import get_prompt_provider


def resolve_prompt_provider(session: AsyncSession) -> BasePromptProvider:
    """为给定会话创建基于数据库的提示词提供者。

    返回一个 :class:`DatabasePromptProvider`，通过 *session* 查询
    ``prompt_templates`` 表。当数据库中不存在匹配模板时，
    提供者会自动回退到 :class:`DefaultPromptProvider`。

    参数：
        session: 活动的异步 SQLAlchemy 会话。

    返回值：
        完整配置的 :class:`BasePromptProvider` 实例。

    异常：
        SQLAlchemyError: 如果会话无效或在提供者初始化期间发生数据库错误。
    """
    return get_prompt_provider("database", session=session)