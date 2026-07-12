"""DeepSeek provider — OpenAI‑compatible LLM provider for DeepSeek API.

Implements :class:`LLMProvider` using the ``AsyncOpenAI`` client.
Merges streaming and non‑streaming calls into a single ``chat`` entry‑point.
"""
from typing import Any, AsyncIterator, Union

from openai import AsyncOpenAI

from .base import LLMProvider


class DeepSeekProvider(LLMProvider):
    """LLM provider for DeepSeek API (OpenAI‑compatible).

    All configuration is injected via constructor parameters.
    The provider is only responsible for calling the LLM API — it does
    **not** read environment variables, config files, or the database.
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        """Initialize the DeepSeek provider.

        Args:
            api_key: DeepSeek API key (required, injected from config).
            base_url: API base URL (required, injected from config).
            model: Default model name (required, injected from config).
        """
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._client: AsyncOpenAI | None = None

    @property
    def _async_client(self) -> AsyncOpenAI:
        """Lazily create and return the ``AsyncOpenAI`` client.

        The client is created once on first access and cached for
        subsequent calls.
        """
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[str, AsyncIterator[str]]:
        """Send a chat completion request to DeepSeek.

        Args:
            messages: List of message dicts with ``role`` and ``content``.
            stream: If ``True``, return an async iterator that yields
                response chunks (SSE) rather than the full response.
            **kwargs: Additional parameters.  Common keys:
                ``model`` (default ``self._model``),
                ``temperature`` (default 0.7),
                ``max_tokens`` (default 2000).

        Returns:
            When ``stream=False``: the complete response as a ``str``.
            When ``stream=True``: an ``AsyncIterator[str]`` yielding
            response tokens.
        """
        model = kwargs.pop("model", self._model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 2000)

        if stream:
            return self._stream_response(messages, model, temperature, max_tokens, **kwargs)

        response = await self._async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        content = response.choices[0].message.content
        return content or ""

    async def _stream_response(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Internal async generator for streaming responses."""
        stream = await self._async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        finally:
            try:
                stream.close()
            except Exception:
                pass
