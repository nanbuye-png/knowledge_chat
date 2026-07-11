"""Prompts package — prompt management abstraction layer.

Exports the base interface, default implementation, and factory function
for downstream consumers.  Import from here instead of reaching into
individual prompt modules.
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
