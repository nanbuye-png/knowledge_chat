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

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .base import BasePromptProvider
from .default import DefaultPromptProvider
from .database import DatabasePromptProvider

# ---------------------------------------------------------------------------
# Prompt provider registry
# ---------------------------------------------------------------------------

SUPPORTED_PROMPTS: dict[str, type[BasePromptProvider]] = {
    "default": DefaultPromptProvider,
    "database": DatabasePromptProvider,
}
"""Mapping from prompt provider name (lowercase) to its concrete class.

Used by :func:`get_prompt_provider` to look up providers.  Registering a
new prompt provider here is the **only** change needed to make it
available to the rest of the system.
"""


def get_prompt_provider(
    name: str | None = None,
    session: Optional[AsyncSession] = None,
) -> BasePromptProvider:
    """Return a prompt provider instance by name.

    When called **without arguments**, defaults to ``"default"``.

    Args:
        name: Prompt provider name (e.g. ``"default"``, ``"database"``).
            If ``None``, defaults to ``"default"``.
        session: An async SQLAlchemy session.  **Required** when *name*
            is ``"database"``; ignored otherwise.

    Returns:
        A fully configured :class:`BasePromptProvider` instance.

    Raises:
        ValueError: If the requested prompt provider name is not
            registered in :data:`SUPPORTED_PROMPTS`, or if
            ``"database"`` is requested without a *session*.

    Example::

        provider = get_prompt_provider()                          # → DefaultPromptProvider
        provider = get_prompt_provider("default")                 # → DefaultPromptProvider
        provider = get_prompt_provider("database", session=db)   # → DatabasePromptProvider
    """
    resolved = (name or "default").lower().strip()

    if resolved == "database":
        if session is None:
            raise ValueError(
                "DatabasePromptProvider requires an AsyncSession. "
                "Pass `session=your_async_session` to get_prompt_provider()."
            )
        return DatabasePromptProvider(session=session)

    provider_cls = SUPPORTED_PROMPTS.get(resolved)
    if provider_cls is None:
        raise ValueError(
            f"Unknown prompt provider: '{resolved}'. "
            f"Currently supported: {', '.join(SUPPORTED_PROMPTS)}"
        )
    return provider_cls()
