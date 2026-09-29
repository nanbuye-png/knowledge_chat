"""检索结果缓存（Phase 3 §5.4 —— Redis 的第一个真实业务场景）。

审计 §5.4 的事实：Redis 协议修好、``init_providers()`` 也接进 lifespan 之后，
``CacheService`` 仍然**零业务引用** —— 缓存层存在，却不解决任何真实问题。
本模块给它第一个真实场景：**RAG 检索结果缓存**。

为什么缓存"检索结果"而不是"回答"
---------------------------------
* 检索结果是**纯函数输出**：同一知识库 + 同一查询 + 同一历史 + 同一 top_k /
  阈值 → 同一结果。重复提问（连续追问、多人问同一个 FAQ）可以直接复用。
* 回答带随机性、且涉及引用时效，缓存回答的风险远大于收益。

Key 设计
--------
``retrieval:v1:{kb_id}:{version}:{fingerprint}:{query_hash}``

* ``version``：该知识库的**版本号**（每次入库完成 / 删除时 +1）；
* ``fingerprint``：影响检索结果的参数（top_k / 阈值 / 检索模式）；
* ``query_hash``：查询 + 对话历史的 SHA-256 摘要（历史会改变 Query Rewrite）。

失效策略（为什么不用 SCAN/KEYS）
-------------------------------
文档变化时只把 ``retrieval:v1:ver:{kb_id}`` 加一，缓存 key 里带版本号 →
旧条目自然"不再被命中"，无需遍历删除（生产 Redis 上 ``KEYS``/``SCAN`` 是禁忌）。
版本号本身不设 TTL：Redis 清库时缓存条目也一并消失，不会出现"读到更旧结果"。
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

from loguru import logger

from ...core.config import settings
from .base import BaseCache

#: 缓存条目结构版本（结构变化时 +1，避免读到旧结构的序列化数据）
CACHE_SCHEMA_VERSION = "v1"

PREFIX_RETRIEVAL = "retrieval"
PREFIX_VERSION = f"{PREFIX_RETRIEVAL}:{CACHE_SCHEMA_VERSION}:ver"


class RetrievalCache:
    """检索结果缓存（默认复用应用级缓存实例：Memory 或 Redis）。"""

    def __init__(
        self,
        cache: Optional[BaseCache] = None,
        *,
        ttl: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self._cache = cache if cache is not None else _get_default_cache()
        self._ttl = ttl
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """是否启用检索缓存（默认读 ``RETRIEVAL_CACHE_ENABLED``）。"""
        if self._enabled is not None:
            return self._enabled
        return bool(getattr(settings, "RETRIEVAL_CACHE_ENABLED", True))

    @property
    def ttl(self) -> int:
        """缓存有效期（秒，默认 ``RETRIEVAL_CACHE_TTL``）。"""
        if self._ttl is not None:
            return self._ttl
        return int(getattr(settings, "RETRIEVAL_CACHE_TTL", 300))

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------

    async def get(
        self,
        knowledge_base_id: int,
        question: str,
        *,
        history_key: str = "",
        fingerprint: str = "",
    ) -> Optional[Any]:
        """读取缓存（命中返回 ``RetrievalResult``，未命中返回 ``None``）。"""
        if not self.enabled:
            return None

        from ..retrieval.models import RetrievalResult

        key = await self._build_key(
            knowledge_base_id,
            question,
            history_key=history_key,
            fingerprint=fingerprint,
        )
        try:
            payload = await self._cache.get(key)
        except Exception as exc:  # noqa: BLE001 - 缓存故障不能影响问答
            logger.warning(f"读检索缓存失败（key={key}）：{exc}")
            return None

        if not isinstance(payload, dict) or "has_results" not in payload:
            # 结构不认识（旧版本条目 / 脏数据）：当作 miss 并清掉，
            # 否则会静默变成"空结果"，把缓存问题伪装成"知识库里没有内容"
            if isinstance(payload, dict):
                logger.warning(f"检索缓存结构不匹配，已丢弃（key={key}）")
                try:
                    await self._cache.delete(key)
                except Exception:  # pragma: no cover - 防御性
                    pass
            return None

        try:
            return RetrievalResult.from_dict(payload)
        except Exception as exc:  # noqa: BLE001 - 旧结构/脏数据同样不能影响问答
            logger.warning(f"检索缓存反序列化失败（key={key}）：{exc}")
            try:
                await self._cache.delete(key)
            except Exception:  # pragma: no cover - 防御性
                pass
            return None

    async def set(
        self,
        knowledge_base_id: int,
        question: str,
        result: Any,
        *,
        history_key: str = "",
        fingerprint: str = "",
    ) -> None:
        """写入缓存（失败只 warning：缓存绝不影响问答）。"""
        if not self.enabled:
            return

        try:
            key = await self._build_key(
                knowledge_base_id,
                question,
                history_key=history_key,
                fingerprint=fingerprint,
            )
            await self._cache.set(key, result.to_dict(), ttl=self.ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"写检索缓存失败（kb={knowledge_base_id}）：{exc}")

    async def invalidate_knowledge_base(self, knowledge_base_id: int) -> None:
        """让该知识库的检索缓存整体失效（版本号 +1，无需遍历删除）。"""
        try:
            key = self._version_key(knowledge_base_id)
            current = await self._cache.get(key)
            version = int(current) + 1 if isinstance(current, int) else 1
            await self._cache.set(key, version, ttl=None)
            logger.info(f"检索缓存失效: kb_id={knowledge_base_id} → version={version}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"检索缓存失效失败（kb={knowledge_base_id}）：{exc}")

    # ------------------------------------------------------------------
    # Key 构造
    # ------------------------------------------------------------------

    @staticmethod
    def _version_key(knowledge_base_id: int) -> str:
        return f"{PREFIX_VERSION}:{knowledge_base_id}"

    async def _build_key(
        self,
        knowledge_base_id: int,
        question: str,
        *,
        history_key: str,
        fingerprint: str,
    ) -> str:
        version = await self._cache.get(self._version_key(knowledge_base_id))
        version = int(version) if isinstance(version, int) else 0
        return (
            f"{PREFIX_RETRIEVAL}:{CACHE_SCHEMA_VERSION}:{knowledge_base_id}:{version}:"
            f"{fingerprint or 'default'}:{self._digest(question + '|' + history_key)}"
        )

    @staticmethod
    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def build_history_key(history: Optional[list[dict]]) -> str:
        """把对话历史压成稳定摘要（历史会改变 Query Rewrite 的结果）。"""
        if not history:
            return ""
        parts = [f"{h.get('role', '')}:{h.get('content', '')}" for h in history[-10:]]
        return RetrievalCache._digest("\n".join(parts))

    @staticmethod
    def build_fingerprint(top_k: Optional[int], min_score: Optional[float]) -> str:
        """影响检索结果的参数指纹（top_k / 阈值 / 检索模式）。"""
        mode = getattr(settings, "RETRIEVAL_MODE", "hybrid")
        return f"k{top_k}-s{min_score}-m{mode}"


def _get_default_cache() -> BaseCache:
    """复用应用级缓存实例（memory 或 redis，由 ProviderFactory 决定）。"""
    from . import get_cache

    return get_cache()
