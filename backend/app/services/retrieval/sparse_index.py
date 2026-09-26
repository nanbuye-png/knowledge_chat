"""Sparse (BM25) index — persistent inverted index backed by SQLite.

为什么是持久化倒排（Phase 1 §5.2 方案 a）
----------------------------------------
文档真实存放在 ChromaDB（持久化），进程会重启、KB 会增删文档。若每次查询
都从向量库拉全量 chunk 重建内存索引，延迟会随语料规模线性恶化。
因此这里用一张 SQLite 表持久化「词项 → chunk」倒排 + 文档长度统计，
查询时只读候选 term 的 postings 即可算出 BM25，无需加载全量语料。

结构
----
``sparse_docs``     chunk 级元数据 + 长度（length 用于 BM25 长度归一化）
``sparse_postings`` (term, chunk_id, tf) 倒排表

一致性
------
* ``add_document_chunks`` 先删除该 document 的旧记录再写入（幂等，重复入库不会重复计分）。
* ``delete_document`` / ``delete_knowledge_base`` / ``delete_user`` 与向量库删除路径对应。
* 索引文件与向量库同级（``SPARSE_INDEX_PATH``），可随时删除后由向量库重建。
"""

from __future__ import annotations

import asyncio
import math
import os
import sqlite3
import threading
from collections import Counter, defaultdict
from typing import Any, Optional

from loguru import logger

from ...core.config import settings
from .tokenizer import tokenize

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS sparse_docs (
        chunk_id     TEXT PRIMARY KEY,
        kb_id        INTEGER NOT NULL,
        user_id      INTEGER,
        document_id  TEXT NOT NULL,
        filename     TEXT NOT NULL,
        chunk_index  INTEGER NOT NULL,
        length       INTEGER NOT NULL,
        text         TEXT NOT NULL,
        page         INTEGER,
        section      TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_sparse_docs_kb ON sparse_docs(kb_id)",
    "CREATE INDEX IF NOT EXISTS ix_sparse_docs_document ON sparse_docs(document_id)",
    """
    CREATE TABLE IF NOT EXISTS sparse_postings (
        term      TEXT NOT NULL,
        chunk_id  TEXT NOT NULL,
        tf        INTEGER NOT NULL,
        PRIMARY KEY (term, chunk_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_sparse_postings_chunk ON sparse_postings(chunk_id)",
)

#: 单次查询最多使用的词项数（停留在 SQLite 变量上限内，并控制延迟）
MAX_QUERY_TERMS = 64


class SparseIndex:
    """SQLite 倒排索引 + BM25 打分。

    Args:
        path: 索引文件路径；默认取 ``settings.SPARSE_INDEX_PATH``。
        k1: BM25 词频饱和参数。
        b: BM25 长度归一化参数。
    """

    def __init__(
        self,
        path: Optional[str] = None,
        k1: Optional[float] = None,
        b: Optional[float] = None,
    ) -> None:
        self.path = path or settings.SPARSE_INDEX_PATH
        self.k1 = settings.SPARSE_BM25_K1 if k1 is None else k1
        self.b = settings.SPARSE_BM25_B if b is None else b
        self._lock = threading.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        self._migrate_schema(conn)
        conn.commit()

    @staticmethod
    def _migrate_schema(conn: sqlite3.Connection) -> None:
        """为既有索引文件补列（引用追溯的 page / section，§5.5）。

        稀疏索引是可重建的派生产物，因此这里做轻量 ALTER TABLE 迁移，
        而不是引入独立的迁移框架。
        """
        existing = {row[1] for row in conn.execute("PRAGMA table_info(sparse_docs)")}
        for column, ddl in (("page", "INTEGER"), ("section", "TEXT")):
            if column not in existing:
                conn.execute(f"ALTER TABLE sparse_docs ADD COLUMN {column} {ddl}")

    async def initialize(self) -> None:
        """Create the index schema if needed (idempotent)."""
        if self._initialized:
            return

        def _init() -> None:
            with self._lock, self._connect() as conn:
                self._ensure_schema(conn)

        await asyncio.to_thread(_init)
        self._initialized = True
        logger.info(f"稀疏索引就绪: {self.path}")

    async def _run(self, fn):
        return await asyncio.to_thread(fn)

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    async def add_document_chunks(
        self,
        document_id: str,
        filename: str,
        chunks: list[str],
        knowledge_base_id: Optional[int] = None,
        user_id: Optional[int] = None,
        pages: Optional[list] = None,
        sections: Optional[list] = None,
    ) -> int:
        """Index *chunks* for *document_id*（幂等：先删旧记录再写）。

        Args:
            pages: 逐 chunk 的页码（§5.5 引用追溯），长度应与 chunks 一致。
            sections: 逐 chunk 的章节名，长度应与 chunks 一致。

        Returns:
            写入的 chunk 数量。
        """
        if not chunks:
            return 0

        rows: list[tuple] = []
        postings: list[tuple] = []
        for index, chunk in enumerate(chunks):
            chunk_id = f"{document_id}_{index}"
            tokens = tokenize(chunk)
            rows.append(
                (
                    chunk_id,
                    knowledge_base_id if knowledge_base_id is not None else -1,
                    user_id,
                    document_id,
                    filename,
                    index,
                    len(tokens),
                    chunk,
                    (pages or [None] * len(chunks))[index],
                    (sections or [None] * len(chunks))[index],
                )
            )
            for term, tf in Counter(tokens).items():
                postings.append((term, chunk_id, tf))

        def _write() -> int:
            with self._lock, self._connect() as conn:
                self._ensure_schema(conn)
                conn.execute(
                    "DELETE FROM sparse_postings WHERE chunk_id IN "
                    "(SELECT chunk_id FROM sparse_docs WHERE document_id = ?)",
                    (document_id,),
                )
                conn.execute(
                    "DELETE FROM sparse_docs WHERE document_id = ?", (document_id,)
                )
                conn.executemany(
                    "INSERT INTO sparse_docs "
                    "(chunk_id, kb_id, user_id, document_id, filename, "
                    " chunk_index, length, text, page, section) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    rows,
                )
                conn.executemany(
                    "INSERT OR REPLACE INTO sparse_postings (term, chunk_id, tf) "
                    "VALUES (?,?,?)",
                    postings,
                )
                conn.commit()
            return len(rows)

        written = await self._run(_write)
        logger.info(
            f"Sparse index: 写入 {written} chunks "
            f"(document={document_id}, kb={knowledge_base_id})"
        )
        return written

    async def delete_document(self, document_id: str) -> int:
        """Remove every chunk of *document_id* from the index."""

        def _delete() -> int:
            with self._lock, self._connect() as conn:
                self._ensure_schema(conn)
                # 先删 postings（此时还能通过 sparse_docs 定位到它们），再删 docs
                conn.execute(
                    "DELETE FROM sparse_postings WHERE chunk_id IN "
                    "(SELECT chunk_id FROM sparse_docs WHERE document_id = ?)",
                    (document_id,),
                )
                cur = conn.execute(
                    "DELETE FROM sparse_docs WHERE document_id = ?", (document_id,)
                )
                conn.commit()
                return cur.rowcount or 0

        return await self._run(_delete)

    async def delete_knowledge_base(self, knowledge_base_id: int) -> int:
        """Remove every chunk of one knowledge base."""

        def _delete() -> int:
            with self._lock, self._connect() as conn:
                self._ensure_schema(conn)
                cur = conn.execute(
                    "DELETE FROM sparse_docs WHERE kb_id = ?", (knowledge_base_id,)
                )
                conn.execute(
                    "DELETE FROM sparse_postings WHERE chunk_id NOT IN "
                    "(SELECT chunk_id FROM sparse_docs)"
                )
                conn.commit()
                return cur.rowcount or 0

        return await self._run(_delete)

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        knowledge_base_id: Optional[int] = None,
        top_k: int = 5,
    ) -> list[dict]:
        """BM25 search over the inverted index.

        Args:
            query: 查询文本（中文按字符 bi-gram 切分）。
            knowledge_base_id: 限定知识库；``None`` 表示全库。
            top_k: 返回条数。

        Returns:
            与向量检索同构的结果列表：
            ``{"id", "document_id", "filename", "chunk_index", "text", "score"}``，
            ``score`` 为 BM25 原始分（>0）。
        """
        terms = list(dict.fromkeys(tokenize(query)))[:MAX_QUERY_TERMS]
        if not terms:
            return []

        def _search() -> list[dict]:
            with self._connect() as conn:
                self._ensure_schema(conn)
                where = "d.kb_id = ?" if knowledge_base_id is not None else "1=1"
                params: list[Any] = [*terms]
                if knowledge_base_id is not None:
                    params.append(knowledge_base_id)
                placeholders = ",".join("?" for _ in terms)
                stats_params = (
                    (knowledge_base_id,) if knowledge_base_id is not None else ()
                )

                stats_row = conn.execute(
                    f"SELECT COUNT(*), COALESCE(AVG(length), 0) FROM sparse_docs d "
                    f"WHERE {where}",
                    stats_params,
                ).fetchone()
                total_docs = stats_row[0] or 0
                avg_len = stats_row[1] or 0.0
                if total_docs == 0:
                    return []

                df_rows = conn.execute(
                    f"SELECT p.term, COUNT(*) FROM sparse_postings p "
                    f"JOIN sparse_docs d ON d.chunk_id = p.chunk_id "
                    f"WHERE p.term IN ({placeholders}) AND {where} "
                    f"GROUP BY p.term",
                    params,
                ).fetchall()
                doc_freq = {term: count for term, count in df_rows}

                rows = conn.execute(
                    f"SELECT p.chunk_id, p.term, p.tf, d.length "
                    f"FROM sparse_postings p "
                    f"JOIN sparse_docs d ON d.chunk_id = p.chunk_id "
                    f"WHERE p.term IN ({placeholders}) AND {where}",
                    params,
                ).fetchall()
                if not rows:
                    return []

                scores: dict[str, float] = defaultdict(float)
                for chunk_id, term, tf, length in rows:
                    df = doc_freq.get(term, 1)
                    idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
                    norm_len = (length / avg_len) if avg_len else 1.0
                    denom = tf + self.k1 * (1 - self.b + self.b * norm_len)
                    scores[chunk_id] += idf * (tf * (self.k1 + 1)) / denom

                ranked = sorted(
                    scores.items(), key=lambda kv: kv[1], reverse=True
                )[:top_k]
                if not ranked:
                    return []

                chunk_ids = [cid for cid, _ in ranked]
                meta_placeholders = ",".join("?" for _ in chunk_ids)
                meta_rows = conn.execute(
                    f"SELECT chunk_id, document_id, filename, chunk_index, text, "
                    f"page, section FROM sparse_docs "
                    f"WHERE chunk_id IN ({meta_placeholders})",
                    chunk_ids,
                ).fetchall()
                meta = {row[0]: row for row in meta_rows}

            results = []
            for chunk_id, score in ranked:
                row = meta.get(chunk_id)
                if row is None:
                    continue
                results.append(
                    {
                        "id": row[0],
                        "document_id": row[1],
                        "filename": row[2],
                        "chunk_index": row[3],
                        "text": row[4],
                        "page": row[5],
                        "section": row[6],
                        "score": score,
                    }
                )
            return results

        return await self._run(_search)

    async def delete_user(self, user_id: int) -> int:
        """Remove every chunk belonging to one user."""

        def _delete() -> int:
            with self._lock, self._connect() as conn:
                self._ensure_schema(conn)
                cur = conn.execute(
                    "DELETE FROM sparse_docs WHERE user_id = ?", (user_id,)
                )
                conn.execute(
                    "DELETE FROM sparse_postings WHERE chunk_id NOT IN "
                    "(SELECT chunk_id FROM sparse_docs)"
                )
                conn.commit()
                return cur.rowcount or 0

        return await self._run(_delete)

    async def count(self) -> int:
        """Total number of indexed chunks."""

        def _count() -> int:
            with self._connect() as conn:
                self._ensure_schema(conn)
                return conn.execute("SELECT COUNT(*) FROM sparse_docs").fetchone()[0]

        return await self._run(_count)

    async def stats(self, knowledge_base_id: Optional[int] = None) -> dict:
        """Return basic index statistics (debug / observability)."""

        def _stats() -> dict:
            with self._connect() as conn:
                self._ensure_schema(conn)
                if knowledge_base_id is None:
                    row = conn.execute(
                        "SELECT COUNT(*), COALESCE(AVG(length), 0) FROM sparse_docs"
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT COUNT(*), COALESCE(AVG(length), 0) FROM sparse_docs "
                        "WHERE kb_id = ?",
                        (knowledge_base_id,),
                    ).fetchone()
                terms = conn.execute(
                    "SELECT COUNT(DISTINCT term) FROM sparse_postings"
                ).fetchone()[0]
                return {
                    "chunks": row[0] or 0,
                    "avg_length": round(row[1] or 0.0, 2),
                    "terms": terms,
                    "path": self.path,
                }

        return await self._run(_stats)


# ---------------------------------------------------------------------------
# Process-wide singleton（与 vector_store 的用法保持一致）
# ---------------------------------------------------------------------------

_sparse_index: Optional[SparseIndex] = None


def get_sparse_index() -> SparseIndex:
    """Return the process-wide :class:`SparseIndex` (created lazily)."""
    global _sparse_index
    if _sparse_index is None:
        _sparse_index = SparseIndex()
    return _sparse_index


def set_sparse_index(index: Optional[SparseIndex]) -> None:
    """Override the singleton（依赖注入 / 测试用）。"""
    global _sparse_index
    _sparse_index = index

