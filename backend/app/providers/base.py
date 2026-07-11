"""Base LLM provider — abstract interface for all LLM providers.

Defines the contract that every concrete provider must implement.
New providers (OpenAI, Gemini, Qwen, etc.) should subclass
``BaseLLMProvider`` and provide implementations for all abstract methods.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, TYPE_CHECKING

if TYPE_CHECKING:
    from .capabilities import ModelCapability  # pragma: no cover


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers.

    Every concrete LLM provider (DeepSeek, Agens, OpenAI, Gemini, Qwen,
    etc.) **must** inherit from this class and implement:

    - :meth:`capabilities` — declare supported features
    - :meth:`chat` — non‑streaming chat completion
    - :meth:`stream_chat` — streaming chat completion (SSE)
    """

    @property
    @abstractmethod
    def capabilities(self) -> "ModelCapability":
        """Return the capability descriptor for this provider.

        Returns:
            A :class:`ModelCapability` instance describing which features
            this provider supports (streaming, tools, vision, json, embeddings).

        Each concrete provider **must** override this property.
        """
        ...

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a non-streaming chat completion request.

        Args:
            messages: A list of message dicts with ``role`` and ``content`` keys.
            **kwargs: Additional provider‑specific parameters (e.g. model,
                temperature, max_tokens).

        Returns:
            The complete response text from the LLM as a single string.
        """
        ...

    @abstractmethod
    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """Send a streaming chat completion request (SSE).

        Args:
            messages: A list of message dicts with ``role`` and ``content`` keys.
            **kwargs: Additional provider‑specific parameters (e.g. model,
                temperature, max_tokens).

        Yields:
            Text tokens (``str``) as they are received from the LLM.
        """
        ...