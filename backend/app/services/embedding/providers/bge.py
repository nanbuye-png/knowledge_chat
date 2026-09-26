"""BGE embedding provider using sentence-transformers.

This is the **runtime embedding path** for the default configuration
(``EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5`` → factory provider ``"bge"``).

Design notes (P0-2)
-------------------
* **显式失败**：模型加载/编码失败一律抛 :class:`EmbeddingError`。
  历史上另一条实现（``providers/default.py``）会返回随机向量，导致
  "上传成功但检索永远是噪声"，本项目不再允许这种静默降级。
* **模型缓存**：``SentenceTransformer`` 按模型名缓存在进程内。此前
  入库流程每处理一个文档都会新建 provider 并重新加载模型（数百 MB，
  数秒），属于纯浪费。
* **检索指令前缀**：BGE 中文模型在 query 侧建议加
  「为这个句子生成表示以用于检索相关文章：」，document 侧不加。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import EmbeddingError, EmbeddingProvider

#: bge-small-zh-v1.5 的输出维度。
BGE_SMALL_ZH_DIM = 512

#: BGE 中文模型的检索指令前缀（**只加在 query 侧**）。
BGE_ZH_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

#: 进程内模型缓存：model_name → SentenceTransformer 实例。
_MODEL_CACHE: dict[str, Any] = {}


def _load_model(model_name: str) -> Any:
    """Load (and cache) a ``SentenceTransformer`` model.

    Args:
        model_name: HuggingFace model identifier.

    Returns:
        The loaded model instance (shared across providers).

    Raises:
        EmbeddingError: If the dependency is missing or loading fails.
    """
    cached = _MODEL_CACHE.get(model_name)
    if cached is not None:
        return cached

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingError(
            "sentence-transformers 未安装，无法使用本地 bge 嵌入模型。"
            "请执行: pip install sentence-transformers"
        ) from exc

    try:
        logger.info(f"Loading embedding model: {model_name}")
        model = SentenceTransformer(model_name)
    except Exception as exc:
        raise EmbeddingError(f"加载嵌入模型失败（{model_name}）: {exc}") from exc

    _MODEL_CACHE[model_name] = model
    logger.info(f"✅ Embedding model loaded: {model_name}")
    return model


class BgeEmbeddingProvider(EmbeddingProvider):
    """BGE 本地嵌入模型（sentence-transformers）。"""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        dim: int = BGE_SMALL_ZH_DIM,
    ):
        self.model_name = model_name
        self.dim = dim
        self._model: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def initialized(self) -> bool:
        """``True`` once the model is available in memory."""
        return self._model is not None

    async def initialize(self) -> None:
        """Load the model (cached process-wide).

        Raises:
            EmbeddingError: If the model cannot be loaded.
        """
        self._model = _load_model(self.model_name)

    async def close(self) -> None:
        """No-op: the model instance is shared through the module cache."""
        return None

    async def _ensure_model(self) -> Any:
        if self._model is None:
            await self.initialize()
        return self._model

    # ------------------------------------------------------------------
    # Embedding API
    # ------------------------------------------------------------------

    async def embed_text(self, text: str) -> list[float]:
        return await self.embed_query(text)

    async def embed_query(self, text: str) -> list[float]:
        """Embed a query — with the BGE retrieval instruction prefix."""
        model = await self._ensure_model()
        try:
            vector = model.encode(
                BGE_ZH_QUERY_INSTRUCTION + text, normalize_embeddings=True
            )
            return vector.tolist()
        except Exception as exc:
            raise EmbeddingError(f"生成查询向量失败: {exc}") from exc

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents — **without** the query instruction prefix."""
        if not texts:
            return []
        model = await self._ensure_model()
        try:
            vectors = model.encode(texts, normalize_embeddings=True)
            return vectors.tolist()
        except Exception as exc:
            raise EmbeddingError(f"生成文档向量失败（{len(texts)} 条）: {exc}") from exc
