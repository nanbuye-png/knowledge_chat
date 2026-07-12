"""LLM Provider factory — creates LLMProvider instances based on configuration.

This module is the **single place** where provider instances are created.
Consumers should call :meth:`LLMProviderFactory.create` instead of importing
and instantiating concrete providers directly.

Supports three provider resolution strategies:

1.  ``settings.LLM_PROVIDER`` — the default provider from ``.env``.
2.  Explicit provider name via ``create_with_name()``.
3.  ``LLMModel`` database object (when provider/model are stored per-record).

To add a new provider:
    1. Write a provider module under ``services/llm/`` that inherits
       :class:`LLMProvider`.
    2. Register it in :data:`_PROVIDERS`.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.llm_model import LLMModel
from app.services.model_registry import get_model_registry

from .base import LLMProvider
from .deepseek_provider import DeepSeekProvider
from .agens_provider import AgensProvider

# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "deepseek": DeepSeekProvider,
    "agens": AgensProvider,
}
"""Mapping from provider name (lowercase) to its concrete class.

Registering a new provider here is the **only** change needed to make
it available to the rest of the system (once the provider module itself
is written).
"""


class LLMProviderFactory:
    """Factory that returns the appropriate :class:`LLMProvider` implementation.

    Usage::

        # Default provider from .env (LLM_PROVIDER)
        provider = LLMProviderFactory.create(settings)

        # Explicit provider
        provider = LLMProviderFactory.create_with_name("agens", settings)

        # From database model
        provider = LLMProviderFactory.create_from_model(llm_model, settings)

        # From database via ModelRegistry (resolves default model)
        provider = await LLMProviderFactory.create_from_registry(db, settings)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        """Create an :class:`LLMProvider` based on ``settings.LLM_PROVIDER``.

        This is the primary entry‑point for the application.  Switch the
        active provider by changing ``LLM_PROVIDER`` in ``.env`` — no code
        changes needed.

        Args:
            settings: Application settings object.

        Returns:
            A concrete :class:`LLMProvider` instance.

        Raises:
            ValueError: If the configured provider name is not registered
                in :data:`_PROVIDERS`.
        """
        provider_name = settings.LLM_PROVIDER.lower().strip()
        return LLMProviderFactory._build(provider_name, settings.LLM_MODEL, settings)

    @staticmethod
    def create_with_name(provider_name: str, settings: Settings) -> LLMProvider:
        """Create a provider by explicit name.

        Args:
            provider_name: Provider name (e.g. ``"deepseek"``, ``"agens"``).
            settings: Application settings object.

        Returns:
            A concrete :class:`LLMProvider` instance.

        Raises:
            ValueError: If *provider_name* is not registered.
        """
        name = provider_name.lower().strip()
        return LLMProviderFactory._build(name, settings.LLM_MODEL, settings)

    @staticmethod
    def create_from_model(model: "LLMModel", settings: Settings) -> LLMProvider:
        """Create a provider from a database ``LLMModel`` record.

        Args:
            model: A database model object with ``.provider`` and
                ``.model_name`` attributes.
            settings: Application settings object.

        Returns:
            A concrete :class:`LLMProvider` instance.

        Raises:
            ValueError: If ``model.provider`` is not registered.
        """
        name = model.provider.lower().strip()
        return LLMProviderFactory._build(name, model.model_name, settings)

    @staticmethod
    async def create_from_registry(
        db: AsyncSession, settings: Settings
    ) -> LLMProvider | None:
        """Create a provider by resolving the default model via :class:`ModelRegistry`.

        This is the **database‑driven** entry‑point.  It queries the
        ``llm_models`` table for the default ``LLMModel`` and delegates
        to :meth:`create_from_model`.

        Args:
            db: An active async SQLAlchemy session.
            settings: Application settings object.

        Returns:
            A concrete :class:`LLMProvider`, or ``None`` if no enabled
            model was found in the registry.
        """
        registry = get_model_registry()
        model = await registry.get_default_model(db)
        if model is None:
            return None
        return LLMProviderFactory.create_from_model(model, settings)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build(provider_name: str, model_name: str, settings: Settings) -> LLMProvider:
        """Build a provider instance from resolved parameters.

        Args:
            provider_name: Lowercased provider name.
            model_name: Model name to use.
            settings: Application settings.

        Returns:
            A configured :class:`LLMProvider` instance.

        Raises:
            ValueError: If *provider_name* is unknown.
        """
        provider_cls = _PROVIDERS.get(provider_name)
        if provider_cls is None:
            raise ValueError(
                f"Unknown LLM provider: '{provider_name}'. "
                f"Currently supported: {', '.join(_PROVIDERS)}"
            )

        if provider_name == "deepseek":
            return provider_cls(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_API_BASE,
                model=model_name,
            )
        if provider_name == "agens":
            return provider_cls(
                api_key=settings.AGENS_API_KEY,
                base_url=settings.AGENS_API_BASE,
                model=model_name,
            )

        # Generic fallback for future providers that follow the convention
        # of having matching setting keys (e.g., OPENAI_API_KEY).
        raise NotImplementedError(
            f"Provider '{provider_name}' is registered but has no build logic yet."
        )
