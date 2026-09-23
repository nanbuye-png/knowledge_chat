"""Agens provider — OpenAI‑compatible LLM provider for Agens API.

Implements :class:`LLMProvider` using the ``AsyncOpenAI`` client.
Merges streaming and non‑streaming calls into a single ``chat`` entry‑point.
"""
from typing import Any, AsyncIterator, Union

from openai import AsyncOpenAI

from .base import LLMProvider, build_llm_http_client


class AgensProvider(LLMProvider):
    """LLM provider for Agens API (OpenAI‑compatible).

    All configuration is injected via constructor parameters.
    The provider is only responsible for calling the LLM API — it does
    **not** read environment variables, config files, or the database.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        disable_proxy: bool = False,
        timeout: float | None = None,
        connect_timeout: float | None = None,
    ) -> None:
        """Initialize the Agens provider.

        Args:
            api_key: Agens API key (required, injected from config).
            base_url: API base URL (required, injected from config).
            model: Default model name (required, injected from config).
            disable_proxy: When ``True``, bypass the system/environment proxy
                (``trust_env=False``) for LLM requests.
            timeout: Read/write timeout in seconds for LLM requests.
            connect_timeout: Connect/pool timeout in seconds for LLM requests.
        """
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._disable_proxy = disable_proxy
        self._timeout = timeout
        self._connect_timeout = connect_timeout
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
                http_client=build_llm_http_client(
                    disable_proxy=self._disable_proxy,
                    timeout=self._timeout,
                    connect_timeout=self._connect_timeout,
                ),
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[str, AsyncIterator[str]]:
        """Send a chat completion request to Agens.

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
        content = response.choices[0].message.content or ""
        # Agens 推理型模型（如 agnes-2.5-flash）正文前会带前导换行，去掉以免前端出现空白段落
        return content.lstrip()

    async def _stream_response(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Internal async generator for streaming responses (with defensive access)."""
        stream_obj = await self._async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        try:
            is_first_chunk = True
            async for chunk in stream_obj:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)

                if not delta:
                    continue

                content = getattr(delta, "content", None)

                if not content:
                    continue

                # Agens 推理型模型（如 agnes-2.5-flash）会先输出 reasoning_content，
                # 正文首个 chunk 带前导换行，这里在首块去除，避免前端出现空白段落。
                if is_first_chunk:
                    content = content.lstrip()
                    if not content:
                        continue
                    is_first_chunk = False

                yield content
        finally:
            close = getattr(stream_obj, "close", None)

            if close:
                result = close()

                if hasattr(result, "__await__"):
                    await result
