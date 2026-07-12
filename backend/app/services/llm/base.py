"""Unified LLM Provider abstract interface.

All concrete LLM providers (DeepSeek, OpenAI, Gemini, etc.) MUST inherit
from :class:`LLMProvider` and implement :meth:`chat`.
"""
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Union


class LLMProvider(ABC):
    """Abstract base class for LLM chat providers.

    Defines a single async entry-point ``chat`` that every provider
    must implement.  Extra provider‑specific parameters (temperature,
    top_p, max_tokens, tools, response_format, …) are passed through
    ``**kwargs`` for forward compatibility.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[str, AsyncIterator[str]]:
        """Send a conversation to the LLM and return the response.

        Args:
            messages: A list of message dicts (e.g.
                ``{"role": "user", "content": "Hello"}``).
            stream: If ``True``, return an async iterator that yields
                response chunks rather than the full response at once.
            **kwargs: Provider‑specific parameters such as
                ``temperature``, ``top_p``, ``max_tokens``,
                ``tools``, ``response_format``, etc.

        Returns:
            When ``stream=False``: the complete response as a ``str``.
            When ``stream=True``: an ``AsyncIterator[str]`` yielding
            response chunks.
        """
        ...