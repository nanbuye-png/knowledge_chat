"""Default Embedding Provider — local model via SentenceTransformer.

Uses HuggingFace SentenceTransformer / Transformers with a local model
(BAAI/bge-small-zh-v1.5 by default).  Falls back to random embeddings
if the model fails to load.

This is a migration of the original :class:`DefaultEmbeddingProvider`
into the ``providers/`` sub‑package.
"""

import numpy as np
from loguru import logger
import torch

from ..base import EmbeddingProvider


class DefaultEmbeddingProvider(EmbeddingProvider):
    """Embedding provider backed by a local HuggingFace model.

    All model loading, encoding, and fallback logic lives here.
    This is the **only** place that imports ``sentence_transformers``
    or ``transformers``.
    """

    def __init__(self, model_name: str, embedding_dim: int) -> None:
        """Initialize the provider (model is loaded lazily via :meth:`initialize`).

        Args:
            model_name: HuggingFace model identifier (e.g. ``"BAAI/bge-small-zh-v1.5"``).
            embedding_dim: Dimensionality for fallback embeddings.
        """
        self._model_name = model_name
        self._embedding_dim = embedding_dim
        self._initialized = False
        self._model = None  # SentenceTransformer or transformers model
        self._tokenizer = None  # Only used with raw transformers fallback

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def initialized(self) -> bool:
        """``True`` once the model has been loaded (or fallback is ready)."""
        return self._initialized

    async def initialize(self) -> None:
        """Load the embedding model into memory.

        Tries ``SentenceTransformer`` first, then falls back to raw
        ``transformers``.  If both fail, random vectors are used — the
        flag ``_initialized`` is still set to ``True`` so consumers
        can continue operating.
        """
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
            self._initialized = True
            logger.info(f"✅ Embedding model loaded: {self._model_name}")
        except ImportError:
            logger.warning("sentence-transformers not installed, trying transformers...")
            try:
                await self._init_transformers()
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                logger.warning("Will use fallback embeddings (random vectors)")
                self._initialized = True
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            logger.warning("Will use fallback embeddings (random vectors)")
            self._initialized = True

    async def _init_transformers(self) -> None:
        """Fallback: load model via raw ``transformers`` + ``torch``."""
        from transformers import AutoTokenizer, AutoModel

        logger.info(f"Loading model via transformers: {self._model_name}")
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        self._model = AutoModel.from_pretrained(self._model_name)
        self._initialized = True
        logger.info("✅ Embedding model loaded via transformers")

    async def close(self) -> None:
        """Release model resources."""
        self._model = None
        self._tokenizer = None
        self._initialized = False
        logger.info("Embedding provider closed")

    # ------------------------------------------------------------------
    # EmbeddingProvider interface
    # ------------------------------------------------------------------

    async def embed_text(self, text: str) -> list[float]:
        """Generate an embedding for a single text.

        Alias for :meth:`embed_query`.  Both methods produce identical
        output — ``embed_text`` is the canonical single‑text entry point.

        Args:
            text: The text to embed.

        Returns:
            A normalized embedding vector, or an empty list on failure.
        """
        return await self.embed_query(text)

    async def embed_query(self, text: str) -> list[float]:
        """Generate an embedding for a single query text.

        Args:
            text: The text to embed (e.g. a user question).

        Returns:
            A normalized embedding vector, or an empty list on failure.
        """
        embeddings = await self.embed_documents([text])
        return embeddings[0] if embeddings else []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of documents.

        Args:
            texts: A list of document texts to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        if not self._initialized or self._model is None:
            logger.warning("Embedding model not loaded, using fallback")
            return self._fallback_embeddings(texts)

        try:
            return await self._encode(texts)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return self._fallback_embeddings(texts)

    # ------------------------------------------------------------------
    # Internal encoding
    # ------------------------------------------------------------------

    async def _encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts via SentenceTransformer or raw transformers.

        Raises:
            Exception: If encoding fails (caught by :meth:`embed_documents`).
        """
        # SentenceTransformer path
        if hasattr(self._model, "encode"):
            embeddings = self._model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            )
            return embeddings.tolist()

        # Raw transformers path
        import torch

        encoded_input = self._tokenizer(
            texts, padding=True, truncation=True, max_length=512, return_tensors="pt"
        )
        with torch.no_grad():
            model_output = self._model(**encoded_input)

        embeddings = self._mean_pooling(
            model_output, encoded_input["attention_mask"]
        )
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        return embeddings.tolist()

    @staticmethod
    def _mean_pooling(model_output, attention_mask) -> "torch.Tensor":
        """Mean pooling — takes attention mask into account."""
        import torch

        token_embeddings = model_output[0]
        input_mask_expanded = (
            attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        )
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
            input_mask_expanded.sum(1), min=1e-9
        )

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _fallback_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic fallback random embeddings."""
        logger.warning(f"Using fallback embeddings for {len(texts)} texts")
        rng = np.random.default_rng(42)
        return [
            rng.uniform(-0.1, 0.1, self._embedding_dim).tolist()
            for _ in texts
        ]