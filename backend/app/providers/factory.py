"""Provider factory — centralizes LLM provider creation.

This module is the **single place** where provider instances are created.
Consumers should call :func:`get_llm_provider` instead of importing and
instantiating concrete providers directly.

Supports three calling conventions (backward compatible):

1.  Default (no argument):
        ``get_llm_provider()``
    Uses ``settings.LLM_PROVIDER`` and ``settings.LLM_MODEL``.

2.  String provider name:
        ``get_llm_provider("deepseek")``
    Uses ``settings.LLM_MODEL`` as the default model.

3.  ``LLMModel`` configuration object:
        ``get_llm_provider(model_config)``
    Reads ``model_config.provider`` and ``model_config.model_name``.

The factory stays independent of the database layer — it only receives
pre‑loaded configuration objects.

To add a new provider
---------------------
1. Register it in :data:`SUPPORTED_PROVIDERS`.
2. Add the corresponding ``if provider_name == ...`` block in
   :func:`get_llm_provider`.

All other code paths (API, services, etc.) remain unchanged.
"""

from typing import Union, TYPE_CHECKING

from ..core.config import settings
from .agens import AgensProvider
from .base import BaseLLMProvider
from .deepseek import DeepSeekProvider

if TYPE_CHECKING:
    from ..models.llm_model import LLMModel  # pragma: no cover — only for type hints

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

SUPPORTED_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "deepseek": DeepSeekProvider,
    "agens": AgensProvider,
}
"""Mapping from provider name (lowercase) to its concrete class.

Used by :func:`get_llm_provider` to look up providers.  Registering a
new provider here is the **only** change needed to make it available
to the rest of the system (once the provider module itself is written).
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_provider_info(
    provider_input: Union[str, "LLMModel", None],
) -> tuple[str, str]:
    """Resolve (provider_name, model_name) from different input types.

    Args:
        provider_input:
            - ``None``: defaults to ``settings.LLM_PROVIDER``.
            - ``str``: provider name (e.g. ``"deepseek"``).
            - ``LLMModel``: database model object.

    Returns:
        A ``(provider_name, model_name)`` tuple, both lowercased/stripped.
    """
    if provider_input is None:
        provider_name = settings.LLM_PROVIDER.lower().strip()
        model_name = settings.LLM_MODEL
    elif isinstance(provider_input, str):
        provider_name = provider_input.lower().strip()
        model_name = settings.LLM_MODEL
    else:
        # LLMModel object (or any object with .provider / .model_name)
        provider_name = provider_input.provider.lower().strip()
        model_name = provider_input.model_name

    return provider_name, model_name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_llm_provider(
    provider_input: Union[str, "LLMModel", None] = None,
) -> BaseLLMProvider:
    """Return a fully configured LLM provider instance.

    When called **without arguments**, defaults to ``settings.LLM_PROVIDER``
    so the active provider can be switched via ``.env`` without any code
    changes.

    Args:
        provider_input:
            - ``None`` (default): uses ``settings.LLM_PROVIDER`` and
              ``settings.LLM_MODEL``.
            - A ``str``: provider name (e.g. ``"deepseek"``, ``"agens"``).
              The model name is taken from ``settings.LLM_MODEL``.
            - An :class:`~models.llm_model.LLMModel` object: reads
              ``.provider`` and ``.model_name``.

    Returns:
        A fully configured :class:`BaseLLMProvider` instance, ready to
        call ``chat()`` or ``stream_chat()``.

    Raises:
        ValueError: If the requested provider name is not registered
            in :data:`SUPPORTED_PROVIDERS`.

    Example::

        # Default provider from .env
        provider = get_llm_provider()

        # Explicit provider
        provider = get_llm_provider("deepseek")

        # From database model
        provider = get_llm_provider(llm_model_record)
    """
    provider_name, model_name = _resolve_provider_info(provider_input)

    provider_cls = SUPPORTED_PROVIDERS.get(provider_name)
    if provider_cls is not None:
        if provider_name == "deepseek":
            return DeepSeekProvider(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_API_BASE,
                model=model_name,
            )
        if provider_name == "agens":
            return AgensProvider(
                api_key=settings.AGENS_API_KEY,
                base_url=settings.AGENS_API_BASE,
                model=model_name,
            )

    raise ValueError(
        f"Unknown LLM provider: '{provider_name}'. "
        f"Currently supported: {', '.join(SUPPORTED_PROVIDERS)}"
    )