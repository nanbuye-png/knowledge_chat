"""OpenAI embedding provider."""
from typing import Optional

from ..base import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding via API."""

    def __init__(self, api_key: str = "", model: str = "text-embedding-3-small", dim: int = 768):
        self.api_key = api_key
        self.model = model
        self.dim = dim

    async def embed_text(self, text: str) -> list[float]:
        return await self.embed_query(text)

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_documents([text])
        return results[0] if results else []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("OpenAI API key not configured")
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)
        resp = await client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]