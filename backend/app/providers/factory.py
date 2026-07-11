"""Provider factory — centralizes LLM provider creation.

This module is the single place where provider instances are created.
Consumers should call get_llm_provider() instead of importing and
instantiating concrete providers directly.
"""

from ..core.config import settings
from .base import BaseLLMProvider
from .deepseek import DeepSeekProvider


def get_llm_provider(provider_name: str = "deepseek") -> BaseLLMProvider:
    """Return a configured LLM provider instance.

    Args:
        provider_name: Name of the provider to create.
                       Currently only "deepseek" is supported.

    Returns:
        A fully configured BaseLLMProvider instance.

    Raises:
        ValueError: If the requested provider is unknown.
    """
    provider_name = provider_name.lower().strip()

    if provider_name == "deepseek":
        return DeepSeekProvider(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_API_BASE,
            model=settings.LLM_MODEL,
        )

    raise ValueError(
        f"Unknown LLM provider: '{provider_name}'. "
        f"Currently supported: deepseek"
    )