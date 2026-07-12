"""提示词工厂 — 集中管理提示词提供者的创建。

本模块是创建提示词提供者实例的 **唯一入口**。
消费者应调用 :func:`get_prompt_provider` 而非直接导入和实例化具体提供者。

新增提示词提供者的步骤
-------------------------
1. 创建一个继承 :class:`BasePromptProvider` 的新类。
2. 在 :data:`SUPPORTED_PROMPTS` 中注册它。
3. 所有其他代码路径保持不变。
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .base import BasePromptProvider
from .default import DefaultPromptProvider
from .database import DatabasePromptProvider

# ---------------------------------------------------------------------------
# 提示词提供者注册表
# ---------------------------------------------------------------------------

SUPPORTED_PROMPTS: dict[str, type[BasePromptProvider]] = {
    "default": DefaultPromptProvider,
    "database": DatabasePromptProvider,
}
"""提示词提供者名称（小写）到其具体类的映射。

由 :func:`get_prompt_provider` 用于查找提供者。在此处注册新的
提示词提供者是使其对系统其余部分可用的 **唯一** 变更。
"""


def get_prompt_provider(
    name: str | None = None,
    session: Optional[AsyncSession] = None,
) -> BasePromptProvider:
    """按名称返回提示词提供者实例。

    当 **无参数** 调用时，默认为 ``"default"``。

    参数：
        name: 提示词提供者名称（如 ``"default"``、``"database"``）。
            如果为 ``None``，则默认为 ``"default"``。
        session: 异步 SQLAlchemy 会话。当 *name* 为 ``"database"``
            时 **必须** 提供；否则忽略。

    返回值：
        完整配置的 :class:`BasePromptProvider` 实例。

    异常：
        ValueError: 如果请求的提示词提供者名称未在
            :data:`SUPPORTED_PROMPTS` 中注册，或者请求
            ``"database"`` 时未提供 *session*。

    示例::

        provider = get_prompt_provider()                          # → DefaultPromptProvider
        provider = get_prompt_provider("default")                 # → DefaultPromptProvider
        provider = get_prompt_provider("database", session=db)   # → DatabasePromptProvider
    """
    resolved = (name or "default").lower().strip()

    if resolved == "database":
        if session is None:
            raise ValueError(
                "DatabasePromptProvider 需要 AsyncSession。"
                "请将 `session=your_async_session` 传递给 get_prompt_provider()。"
            )
        return DatabasePromptProvider(session=session)

    provider_cls = SUPPORTED_PROMPTS.get(resolved)
    if provider_cls is None:
        raise ValueError(
            f"未知的提示词提供者: '{resolved}'。"
            f"当前支持的: {', '.join(SUPPORTED_PROMPTS)}"
        )
    return provider_cls()