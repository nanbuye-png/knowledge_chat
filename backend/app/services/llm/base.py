"""Unified LLM Provider abstract interface.

All concrete LLM providers (DeepSeek, OpenAI, Gemini, etc.) MUST inherit
from :class:`LLMProvider` and implement :meth:`chat`.
"""
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Union

import httpx


def build_llm_http_client(
    disable_proxy: bool = False,
    timeout: float | None = None,
    connect_timeout: float | None = None,
) -> httpx.AsyncClient:
    """Build a shared ``httpx.AsyncClient`` for LLM providers.

    Centralises proxy and timeout handling so that LLM API calls do not
    silently depend on the ambient system/environment proxy (e.g. Clash on
    ``127.0.0.1:7897``) unless explicitly allowed via ``disable_proxy=False``.

    Args:
        disable_proxy: When ``True``, set ``trust_env=False`` to bypass any
            proxy configured at the OS/environment level.
        timeout: Read/write timeout in seconds (default 120).  Applies to the
            time between successive chunks of a streaming response.
        connect_timeout: Connect/pool timeout in seconds (default 10).

    Returns:
        A configured :class:`httpx.AsyncClient` ready to be passed as the
        ``http_client`` of an ``AsyncOpenAI`` instance.
    """
    return httpx.AsyncClient(
        trust_env=not disable_proxy,
        timeout=httpx.Timeout(
            connect=connect_timeout if connect_timeout is not None else 10.0,
            read=timeout if timeout is not None else 120.0,
            write=timeout if timeout is not None else 120.0,
            pool=connect_timeout if connect_timeout is not None else 10.0,
        ),
    )


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