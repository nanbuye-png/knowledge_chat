"""Prompt factory — centralizes prompt provider creation.

This module is the **single place** where prompt provider instances
are created.  Consumers should call :func:`get_prompt_provider` instead
of importing and instantiating concrete providers directly.

To add a new prompt provider
-----------------------------
1. Create a new class inheriting from :class:`BasePromptProvider`.
2. Register it in :data:`SUPPORTED_PROMPTS`.
3. All other code paths remain unchanged.
"""

from .base import BasePromptProvider
from .default import DefaultPromptProvider

# ---------------------------------------------------------------------------
# Prompt provider registry
# ---------------------------------------------------------------------------

SUPPORTED_PROMPTS: dict[str, type[BasePromptProvider]] = {
    "default": DefaultPromptProvider,
}
"""Mapping from prompt provider name (lowercase) to its concrete class.

Used by :func:`get_prompt_provider` to look up providers.  Registering a
new prompt provider here is the **only** change needed to make it
available to the rest of the system.
"""


def get_prompt_provider(name: str | None = None) -> BasePromptProvider:
    """Return a prompt provider instance by name.

    When called **without arguments**, defaults to ``"default"``.

    Args:
        name: Prompt provider name (e.g. ``"default"``).  If ``None``,
            defaults to ``"default"``.

    Returns:
        A fully configured :class:`BasePromptProvider` instance.

    Raises:
        ValueError: If the requested prompt provider name is not
            registered in :data:`SUPPORTED_PROMPTS`.

    Example::

        provider = get_prompt_provider()           # → DefaultPromptProvider
        provider = get_prompt_provider("default")  # → DefaultPromptProvider
    """
    resolved = (name or "default").lower().strip()
    provider_cls = SUPPORTED_PROMPTS.get(resolved)
    if provider_cls is None:
        raise ValueError(
            f"Unknown prompt provider: '{resolved}'. "
            f"Currently supported: {', '.join(SUPPORTED_PROMPTS)}"
        )
    return provider_cls()