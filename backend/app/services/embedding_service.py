import numpy as np
from loguru import logger
from ..core.config import settings


class EmbeddingService:
    """
    Service for generating text embeddings.
    
    Uses HuggingFace Transformers with a local model (BAAI/bge-small-zh-v1.5).
    Falls back to random embeddings if the model fails to load.
    """

    def __init__(self):
        self._initialized = False
        self._model = None

    async def initialize(self):
        """Initialize the embedding model."""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            self._initialized = True
            logger.info(f"✅ Embedding model loaded: {settings.EMBEDDING_MODEL}")
        except ImportError:
            logger.warning("sentence-transformers not installed, trying transformers...")
            try:
                await self._init_transformers()
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                logger.warning("Will use fallback embeddings (random vectors)")
                self._initialized = True  # Still allow operation with fallback
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            logger.warning("Will use fallback embeddings (random vectors)")
            self._initialized = True  # Still allow operation with fallback

    async def _init_transformers(self):
        """Fallback: use transformers library directly."""
        from transformers import AutoTokenizer, AutoModel
        import torch
        import torch.nn.functional as F

        logger.info(f"Loading model via transformers: {settings.EMBEDDING_MODEL}")
        self._tokenizer = AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL)
        self._model = AutoModel.from_pretrained(settings.EMBEDDING_MODEL)
        self._initialized = True
        logger.info(f"✅ Embedding model loaded via transformers")

    def _mean_pooling(self, model_output, attention_mask):
        """Mean pooling for transformer embeddings."""
        import torch
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        if not self._initialized or self._model is None:
            logger.warning("Embedding model not loaded, using fallback")
            return self._fallback_embeddings(texts)

        try:
            return await self._embed_local(texts)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return self._fallback_embeddings(texts)

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using local model."""
        try:
            # Try sentence-transformers first
            if hasattr(self._model, 'encode'):
                embeddings = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                return embeddings.tolist()
            
            # Fallback to raw transformers
            import torch
            encoded_input = self._tokenizer(
                texts, padding=True, truncation=True, max_length=512, return_tensors='pt'
            )
            with torch.no_grad():
                model_output = self._model(**encoded_input)
            
            embeddings = self._mean_pooling(model_output, encoded_input['attention_mask'])
            # Normalize
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Local embedding failed: {e}")
            raise

    def _fallback_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate fallback random embeddings when model is unavailable."""
        logger.warning(f"Using fallback embeddings for {len(texts)} texts")
        rng = np.random.default_rng(42)
        return [rng.uniform(-0.1, 0.1, settings.EMBEDDING_DIM).tolist() for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query text."""
        embeddings = await self.embed_texts([text])
        return embeddings[0] if embeddings else []

    async def close(self):
        """Clean up resources."""
        self._model = None
        self._initialized = False
        logger.info("Embedding service closed")


# Singleton instance
embedding_service = EmbeddingService()
