from abc import ABC, abstractmethod
from typing import AsyncGenerator, TYPE_CHECKING

if TYPE_CHECKING:
    from .capabilities import ModelCapability  # pragma: no cover


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    All LLM providers (DeepSeek, OpenAI, Gemini, Agens, etc.) must inherit
    from this class and implement the abstract methods.
    """

    @property
    @abstractmethod
    def capabilities(self) -> "ModelCapability":
        """Return the capability descriptor for this provider.

        Each concrete provider must implement this property to declare
        which features it supports (streaming, tools, vision, etc.).
        """
        ...

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a non-streaming chat completion request.

        Args:
            messages: A list of message dicts with 'role' and 'content' keys.
            **kwargs: Additional provider-specific parameters.

        Returns:
            The complete response text from the LLM.
        """
        ...

    @abstractmethod
    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """Send a streaming chat completion request.

        Args:
            messages: A list of message dicts with 'role' and 'content' keys.
            **kwargs: Additional provider-specific parameters.

        Yields:
            Text tokens as they are received from the LLM.
        """
        ...