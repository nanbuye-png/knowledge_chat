"""Capability checker — validates provider capabilities at runtime.

Provides a lightweight guard layer that services can use to verify a
provider supports a requested feature **before** attempting to use it.
Raises :class:`ValueError` with a clear message when a capability is absent.

Usage::

    checker = CapabilityChecker()
    checker.check_stream(provider)

    # Or use static methods directly:
    CapabilityChecker.check_tools(provider)
"""

from .base import BaseLLMProvider


class CapabilityChecker:
    """Validates provider capabilities against requested features.

    All check methods are **static**, so the class can be used with or
    without instantiation::

        CapabilityChecker.check_stream(provider)       # static call
        CapabilityChecker().check_stream(provider)     # instance call

    Use Scenario
    ------------
    Before calling ``provider.stream_chat()`` or enabling a UI toggle
    for a feature (e.g. JSON mode), validate the capability first::

        CapabilityChecker.check_stream(provider)
        async for token in provider.stream_chat(messages):
            ...
    """

    @staticmethod
    def check_stream(provider: BaseLLMProvider) -> None:
        """Ensure the provider supports streaming (SSE) responses.

        Args:
            provider: The LLM provider instance to check.

        Raises:
            ValueError: If the provider does not support streaming.

        Use Scenario:
            Call before ``provider.stream_chat()``.
        """
        if not provider.capabilities.supports_stream:
            raise ValueError(
                f"Provider {_provider_label(provider)} does not support streaming"
            )

    @staticmethod
    def check_tools(provider: BaseLLMProvider) -> None:
        """Ensure the provider supports tool / function calling.

        Args:
            provider: The LLM provider instance to check.

        Raises:
            ValueError: If the provider does not support tools.

        Use Scenario:
            Call before passing ``tools`` parameter to chat completion.
        """
        if not provider.capabilities.supports_tools:
            raise ValueError(
                f"Provider {_provider_label(provider)} does not support tools"
            )

    @staticmethod
    def check_json(provider: BaseLLMProvider) -> None:
        """Ensure the provider supports JSON / structured output mode.

        Args:
            provider: The LLM provider instance to check.

        Raises:
            ValueError: If the provider does not support JSON mode.

        Use Scenario:
            Call before enabling ``response_format={"type": "json_object"}``.
        """
        if not provider.capabilities.supports_json:
            raise ValueError(
                f"Provider {_provider_label(provider)} does not support JSON mode"
            )

    @staticmethod
    def check_vision(provider: BaseLLMProvider) -> None:
        """Ensure the provider supports vision / image inputs.

        Args:
            provider: The LLM provider instance to check.

        Raises:
            ValueError: If the provider does not support vision.

        Use Scenario:
            Call before sending image data in messages.
        """
        if not provider.capabilities.supports_vision:
            raise ValueError(
                f"Provider {_provider_label(provider)} does not support vision"
            )


def _provider_label(provider: BaseLLMProvider) -> str:
    """Return a human‑readable label for the provider.

    Args:
        provider: The LLM provider instance.

    Returns:
        The provider's class name (e.g. ``"DeepSeekProvider"``).
    """
    return type(provider).__name__