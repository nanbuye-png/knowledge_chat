"""Agens Provider — LLM provider for Agens API (assumed OpenAI-compatible).

This provider assumes the Agens API is OpenAI-compatible and uses
AsyncOpenAI under the hood.  If the actual Agens API diverges from
the OpenAI chat-completion contract, the adapter logic should be
contained within this module without affecting callers.

Note:
    Agens API compatibility is an assumption at this stage.
    The provider will be validated when the Agens endpoint and
    credentials are available.
"""

from typing import AsyncGenerator

from loguru import logger
from openai import AsyncOpenAI

from .base import BaseLLMProvider
from .capabilities import ModelCapability


class AgensProvider(BaseLLMProvider):
    """LLM provider for Agens API (assumed OpenAI-compatible).

    All configuration is injected via constructor parameters.
    The provider is only responsible for calling the LLM API.
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        """Initialize the Agens provider.

        Args:
            api_key: Agens API key (required, injected from config/factory).
            base_url: API base URL (required, injected from config/factory).
            model: Default model name (required, injected from config/factory).
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._client: AsyncOpenAI | None = None
        self._capabilities = ModelCapability(
            supports_stream=True,
            supports_tools=False,
            supports_vision=False,
            supports_json=False,
            supports_embeddings=False,
        )

    # ------------------------------------------------------------------
    # BaseLLMProvider abstract interface
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> ModelCapability:
        """Return the capability descriptor for Agens."""
        return self._capabilities

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
        """Send a non-streaming chat completion request to Agens.

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
        """Send a streaming chat completion request to Agens.

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
