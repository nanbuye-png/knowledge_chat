"""Jina AI embedding provider."""
from typing import Optional
import aiohttp

from ..base import EmbeddingProvider


class JinaEmbeddingProvider(EmbeddingProvider):
    """Jina AI embedding via API."""

    def __init__(self, api_key: str = "", model: str = "jina-embeddings-v3", dim: int = 768):
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self._base_url = "https://api.jina.ai/v1/embeddings"

    async def embed_text(self, text: str) -> list[float]:
        return await self.embed_query(text)

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_documents([text])
        return results[0] if results else []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("Jina API key not configured")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts}
            ) as resp:
                data = await resp.json()
                return [item["embedding"] for item in data["data"]]