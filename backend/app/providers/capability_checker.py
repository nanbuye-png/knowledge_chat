"""Capability checker — validates provider capabilities at runtime.

Provides a lightweight guard layer that services can use to verify a
provider supports a requested feature before attempting to use it.
Raises ``ValueError`` with a clear message when a capability is absent.
"""

from .base import BaseLLMProvider


class CapabilityChecker:
    """Validates provider capabilities against requested features.

    Usage::

        checker = CapabilityChecker()
        checker.check_stream(provider)
        checker.check_tools(provider)

    All check methods are static so the class can be used without
    instantiation if preferred.
    """

    @staticmethod
    def check_stream(provider: BaseLLMProvider) -> None:
        """Ensure the provider supports streaming (SSE) responses.

        Raises:
            ValueError: If the provider does not support streaming.
        """
        if not provider.capabilities.supports_stream:
            raise ValueError(
                f"Provider {_provider_label(provider)} does not support streaming"
            )

    @staticmethod
    def check_tools(provider: BaseLLMProvider) -> None:
        """Ensure the provider supports tool / function calling.

        Raises:
            ValueError: If the provider does not support tools.
        """
        if not provider.capabilities.supports_tools:
            raise ValueError(
                f"Provider {_provider_label(provider)} does not support tools"
            )

    @staticmethod
    def check_json(provider: BaseLLMProvider) -> None:
        """Ensure the provider supports JSON / structured output mode.

        Raises:
            ValueError: If the provider does not support JSON mode.
        """
        if not provider.capabilities.supports_json:
            raise ValueError(
                f"Provider {_provider_label(provider)} does not support JSON mode"
            )

    @staticmethod
    def check_vision(provider: BaseLLMProvider) -> None:
        """Ensure the provider supports vision / image inputs.

        Raises:
            ValueError: If the provider does not support vision.
        """
        if not provider.capabilities.supports_vision:
            raise ValueError(
                f"Provider {_provider_label(provider)} does not support vision"
            )


def _provider_label(provider: BaseLLMProvider) -> str:
    """Return a human-readable label for the provider."""
    return type(provider).__name__