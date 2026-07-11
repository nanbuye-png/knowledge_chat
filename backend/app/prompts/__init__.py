"""Prompts package — prompt management abstraction layer.

Exports the base prompt provider interface and default implementation
for downstream consumers.  Import from here instead of reaching into
individual prompt modules.
"""

from .base import BasePromptProvider
from .default import DefaultPromptProvider

__all__ = [
    "BasePromptProvider",
    "DefaultPromptProvider",
]