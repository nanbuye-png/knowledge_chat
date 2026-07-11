"""Prompt Provider Resolver — runtime prompt provider selection.

Provides :func:`resolve_prompt_provider` which creates a
:class:`DatabasePromptProvider` backed by the given async session.
The returned provider attempts to load templates from the database
first, falling back to the default provider when no matching template
is found.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BasePromptProvider
from .factory import get_prompt_provider


def resolve_prompt_provider(session: AsyncSession) -> BasePromptProvider:
    """Create a database‑backed prompt provider for the given session.

    Returns a :class:`DatabasePromptProvider` that queries the
    ``prompt_templates`` table via *session*.  When no matching template
    exists in the database, the provider automatically falls back to
    :class:`DefaultPromptProvider`.

    Args:
        session: An active async SQLAlchemy session.

    Returns:
        A fully configured :class:`BasePromptProvider` instance.

    Raises:
        SQLAlchemyError: If the session is not valid or a database
            error occurs during provider initialisation.
    """
    return get_prompt_provider("database", session=session)