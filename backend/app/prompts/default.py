"""Default Prompt Provider — standard prompt implementation.

Provides a sensible default prompt strategy suitable for most
knowledge‑base assistant scenarios.  This provider can be swapped
out via dependency injection without modifying any service code.
"""

from .base import BasePromptProvider


class DefaultPromptProvider(BasePromptProvider):
    """Default prompt provider for knowledge‑base AI assistant.

    Implements the standard prompt templates used by the system.
    Subclass or replace this provider to customise prompt behaviour
    without touching :mod:`chat_service` or API layers.

    Usage::

        provider = DefaultPromptProvider()
        print(provider.system_prompt)
        rag_prompt = provider.build_rag_prompt(ctx, q)
        chat_prompt = provider.build_chat_prompt(msg)
    """

    # ------------------------------------------------------------------
    # BasePromptProvider interface
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        """Return the default system prompt for the knowledge‑base assistant.

        Returns:
            A concise system prompt defining the assistant's persona
            and behaviour.
        """
        return "你是一名专业的知识库 AI 助手。请根据提供的资料准确、简洁地回答用户问题。"

    def build_rag_prompt(self, context: str, question: str) -> str:
        """Build a RAG prompt that constrains answers to reference material.

        Args:
            context: Retrieved document chunks as a single string.
            question: The user's original question.

        Returns:
            A formatted prompt string instructing the LLM to answer
            based only on the provided context.
        """
        return (
            f"请仅根据以下参考知识回答问题。\n"
            f"\n"
            f"【参考知识】\n"
            f"{context}\n"
            f"\n"
            f"【用户问题】\n"
            f"{question}\n"
            f"\n"
            f"请仅根据参考知识回答。如果参考知识中没有相关信息，请明确说明'当前资料库中暂无相关信息'。"
        )

    def build_chat_prompt(self, message: str) -> str:
        """Build a simple general‑chat prompt.

        Args:
            message: The user's chat message.

        Returns:
            A plain prompt string wrapping the user message.
        """
        return f"【用户】\n{message}"