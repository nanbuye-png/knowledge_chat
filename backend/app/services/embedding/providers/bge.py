"""BGE embedding provider using sentence-transformers."""
from typing import Optional

from ..base import EmbeddingProvider


class BgeEmbeddingProvider(EmbeddingProvider):
    """BGE local embedding via sentence-transformers."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", dim: int = 768):
        self.model_name = model_name
        self.dim = dim
        self._model = None

    async def initialize(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        except ImportError:
            raise RuntimeError("sentence-transformers not installed")

    async def embed_text(self, text: str) -> list[float]:
        return await self.embed_query(text)

    async def embed_query(self, text: str) -> list[float]:
        if not self._model:
            await self.initialize()
        vec = self._model.encode(text, normalize_embeddings=True).tolist()
        return vec

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self._model:
            await self.initialize()
        vecs = self._model.encode(texts, normalize_embeddings=True).tolist()
        return vecs