"""Prompts package — prompt management abstraction layer.

Exports the base prompt provider interface for downstream consumers.
Import from here instead of reaching into individual prompt modules.
"""

from .base import BasePromptProvider

__all__ = [
    "BasePromptProvider",
]