"""Database Prompt Provider — loads prompt templates from the database.

Provides a :class:`DatabasePromptProvider` that reads prompt templates
from the ``prompt_templates`` table at runtime.  When no matching template
is found in the database, it falls back to a configured
:class:`BasePromptProvider` (defaulting to :class:`DefaultPromptProvider`).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from .base import BasePromptProvider
from .default import DefaultPromptProvider
from ..models.prompt_template import PromptTemplate


async def _query_template(
    session: AsyncSession, prompt_type: str
) -> PromptTemplate | None:
    """Query the database for an enabled template of the given type.

    Args:
        session: An active async SQLAlchemy session.
        prompt_type: The ``prompt_type`` value to look up (e.g. ``"chat"``, ``"rag"``).

    Returns:
        The first matching :class:`PromptTemplate` ordered by ``id``
        ascending, or ``None`` if no enabled template exists.

    Raises:
        SQLAlchemyError: Any database error is propagated to the caller.
    """
    stmt = (
        select(PromptTemplate)
        .where(
            PromptTemplate.prompt_type == prompt_type,
            PromptTemplate.enabled == True,  # noqa: E712
        )
        .order_by(PromptTemplate.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


class DatabasePromptProvider(BasePromptProvider):
    """Prompt provider that reads templates from the ``prompt_templates`` table.

    Every prompt method first tries to load the corresponding template from
    the database (``prompt_type`` = ``"chat"`` / ``"rag"``, ``enabled = True``).
    If a matching record is found its ``content`` is used (with optional
    ``str.format`` interpolation).  Otherwise the request is delegated to
    *fallback_provider*.

    Usage::

        provider = DatabasePromptProvider(session=db)
        # or with a custom fallback:
        provider = DatabasePromptProvider(
            session=db,
            fallback_provider=CustomPromptProvider(),
        )

    Args:
        session: An async SQLAlchemy session used for all DB queries.
        fallback_provider: A :class:`BasePromptProvider` used when no
            matching template exists in the database.  Defaults to
            :class:`DefaultPromptProvider`.
    """

    def __init__(
        self,
        session: AsyncSession,
        fallback_provider: BasePromptProvider | None = None,
    ) -> None:
        self._session = session
        self._fallback = fallback_provider or DefaultPromptProvider()
        logger.debug("DatabasePromptProvider initialised")

    # ------------------------------------------------------------------
    # BasePromptProvider interface (async variants)
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        """Synchronous accessor — returns fallback system prompt.

        DatabasePromptProvider requires async I/O for database access.
        For synchronous contexts, the fallback provider's system prompt
        is returned directly.

        Use :meth:`get_system_prompt` for database‑backed resolution.
        """
        return self._fallback.system_prompt

    async def get_system_prompt(self) -> str:
        """Resolve the system prompt from the database or fallback.

        Looks for a template with ``prompt_type == "chat"`` and
        ``enabled == True``.

        Returns:
            The ``content`` of the matching template, or the
            fallback provider's ``system_prompt``.
        """
        template = await _query_template(self._session, "chat")
        if template is not None:
            logger.debug("Using system prompt from database (id={})".format(template.id))
            return template.content
        logger.debug("No database system prompt found — using fallback")
        return self._fallback.system_prompt

    def build_rag_prompt(self, context: str, question: str) -> str:
        """Synchronous RAG prompt — delegates to fallback provider.

        For async context see :meth:`get_rag_prompt`.
        """
        return self._fallback.build_rag_prompt(context, question)

    async def get_rag_prompt(self, context: str, question: str) -> str:
        """Build RAG prompt from the database or fallback.

        Looks for a template with ``prompt_type == "rag"`` and
        ``enabled == True``.  If found, formats ``content`` with
        ``context`` and ``question`` via :meth:`str.format`.

        Args:
            context: Retrieved document chunks.
            question: The user's question.

        Returns:
            A formatted prompt string.
        """
        template = await _query_template(self._session, "rag")
        if template is not None:
            try:
                formatted = template.content.format(context=context, question=question)
                logger.debug("Using RAG prompt from database (id={})".format(template.id))
                return formatted
            except KeyError as exc:
                logger.warning(
                    "RAG template content missing placeholder: {} — falling back".format(exc)
                )
        logger.debug("No database RAG prompt found — using fallback")
        return self._fallback.build_rag_prompt(context, question)

    def build_chat_prompt(self, message: str) -> str:
        """Synchronous chat prompt — delegates to fallback provider.

        For async context see :meth:`get_chat_prompt`.
        """
        return self._fallback.build_chat_prompt(message)

    async def get_chat_prompt(self, message: str) -> str:
        """Build chat prompt from the database or fallback.

        Looks for a template with ``prompt_type == "chat"`` and
        ``enabled == True``.  If found, formats ``content`` with
        ``message`` via :meth:`str.format`.

        Args:
            message: The user's chat message.

        Returns:
            A formatted prompt string.
        """
        template = await _query_template(self._session, "chat")
        if template is not None:
            try:
                formatted = template.content.format(message=message)
                logger.debug("Using chat prompt from database (id={})".format(template.id))
                return formatted
            except KeyError as exc:
                logger.warning(
                    "Chat template content missing placeholder: {} — falling back".format(exc)
                )
        logger.debug("No database chat prompt found — using fallback")
        return self._fallback.build_chat_prompt(message)