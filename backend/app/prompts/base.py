"""Base Prompt Provider — abstract interface for prompt management.

Defines the contract that every prompt provider must implement.
Prompt providers are responsible for constructing system prompts,
RAG prompts, and general chat prompts.
"""

from abc import ABC, abstractmethod


class BasePromptProvider(ABC):
    """Abstract base class for all prompt providers.

    Prompt providers encapsulate the logic for building prompts sent to
    the LLM.  Different providers can supply different system prompts
    (e.g. a strict knowledge‑base assistant vs. a creative writing bot)
    while the rest of the system remains unchanged.

    Every concrete prompt provider **must** implement:

    - :attr:`system_prompt` — the system‑level instruction for the LLM
    - :meth:`build_rag_prompt` — build a retrieval‑augmented prompt
    - :meth:`build_chat_prompt` — build a general chat prompt
    """

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system‑level prompt for the LLM.

        This prompt is typically sent as the first message with role
        ``"system"``, defining the assistant's persona, behaviour
        constraints, and response style.

        Returns:
            A string containing the system prompt.
        """
        ...

    @abstractmethod
    def build_rag_prompt(self, context: str, question: str) -> str:
        """Build a RAG (Retrieval‑Augmented Generation) prompt.

        Combines the retrieved document context with the user's question
        into a single prompt that instructs the LLM to answer based on
        the provided materials.

        Args:
            context: The retrieved document chunks as a single string.
            question: The user's original question.

        Returns:
            A complete prompt string ready to send to the LLM.
        """
        ...

    @abstractmethod
    def build_chat_prompt(self, message: str) -> str:
        """Build a general chat prompt.

        Wraps the user's message for a free‑form conversation without
        document context.  May include additional instructions (e.g.
        response language, tone) depending on the provider.

        Args:
            message: The user's chat message.

        Returns:
            A prompt string ready to send to the LLM.
        """
        ...