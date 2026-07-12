"""提示词包 — 提示词管理抽象层。

对外导出基础接口、默认实现和工厂函数。
下游消费者应从此处导入，而非直接引用单个提示词模块。
"""

from .base import BasePromptProvider
from .default import DefaultPromptProvider
from .database import DatabasePromptProvider
from .factory import get_prompt_provider, SUPPORTED_PROMPTS

__all__ = [
    "BasePromptProvider",
    "DefaultPromptProvider",
    "DatabasePromptProvider",
    "SUPPORTED_PROMPTS",
    "get_prompt_provider",
]