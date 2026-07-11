from typing import AsyncGenerator

from loguru import logger
from openai import AsyncOpenAI

from .base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """LLM provider for DeepSeek API (OpenAI-compatible).

    All configuration is injected via constructor parameters.
    The provider is only responsible for calling the LLM API.
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        """Initialize the DeepSeek provider.

        Args:
            api_key: DeepSeek API key (required, injected from config).
            base_url: API base URL (required, injected from config).
            model: Default model name (required, injected from config).
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        """Lazily create and return the AsyncOpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    async def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a non-streaming chat completion request to DeepSeek.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional parameters (model, temperature, max_tokens, etc.).

        Returns:
            The complete response text.
        """
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 2000)

        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return response.choices[0].message.content

    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """Send a streaming chat completion request to DeepSeek.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional parameters (model, temperature, max_tokens, etc.).

        Yields:
            Text tokens as they are received.
        """
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 2000)

        stream = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        try:
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        finally:
            try:
                stream.close()
            except Exception:
                pass
