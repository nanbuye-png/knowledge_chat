"""Provider factory — centralizes LLM provider creation.

This module is the single place where provider instances are created.
Consumers should call get_llm_provider() instead of importing and
instantiating concrete providers directly.

Supports two calling conventions (backward compatible):

1.  String provider name:
        get_llm_provider("deepseek")
    Uses settings.LLM_MODEL as the default model.

2.  LLMModel configuration object:
        get_llm_provider(model_config)
    Reads model_config.provider and model_config.model_name.

The factory itself stays independent of the database layer —
it only receives pre‑loaded configuration objects.
"""

from typing import Union, TYPE_CHECKING

from ..core.config import settings
from .base import BaseLLMProvider
from .deepseek import DeepSeekProvider

if TYPE_CHECKING:
    from ..models.llm_model import LLMModel  # pragma: no cover — only for type hints


def _resolve_provider_info(
    provider_input: Union[str, "LLMModel"],
) -> tuple[str, str]:
    """Resolve (provider_name, model_name) from different input types."""
    if isinstance(provider_input, str):
        provider_name = provider_input.lower().strip()
        model_name = settings.LLM_MODEL
    else:
        # LLMModel object (or any object with .provider / .model_name)
        provider_name = provider_input.provider.lower().strip()
        model_name = provider_input.model_name

    return provider_name, model_name


def get_llm_provider(
    provider_input: Union[str, "LLMModel"] = "deepseek",
) -> BaseLLMProvider:
    """Return a configured LLM provider instance.

    Args:
        provider_input:
            - A string: provider name (e.g. "deepseek").
              The model name is taken from settings.LLM_MODEL.
            - An LLMModel object: reads .provider and .model_name.

    Returns:
        A fully configured BaseLLMProvider instance.

    Raises:
        ValueError: If the requested provider is unknown.
    """
    provider_name, model_name = _resolve_provider_info(provider_input)

    if provider_name == "deepseek":
        return DeepSeekProvider(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_API_BASE,
            model=model_name,
        )

    raise ValueError(
        f"Unknown LLM provider: '{provider_name}'. "
        f"Currently supported: deepseek"
    )
