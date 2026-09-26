"""Citation validation — 防止"模型自造引用"，并检查引用是否指向已删除的文档（§5.5）。

两类校验：

1. **一致性校验**（不依赖数据库）
   * 引用必须来自本次真实检索到的 chunk（``document_id`` + ``chunk_index`` 命中）；
   * 答案中出现的 ``[来源N]`` 标记必须落在本次上下文范围内（``1 <= N <= len(context)``）。
2. **存活校验**（需要 DB）
   * 引用指向的 ``document_id`` 必须仍存在于 ``documents`` 表中，
     否则该引用已随文档删除而失效，不应再展示。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Citation

#: 答案中的引用标记，如 [来源1] / ［来源12］
REFERENCE_PATTERN = re.compile(r"[\[［]\s*来源\s*(\d+)\s*[\]］]")


@dataclass
class CitationValidation:
    """一致性校验结果。

    Attributes:
        total: 参与校验的引用数。
        valid: 通过校验的引用。
        invalid: 与本次上下文不一致的引用。
        referenced_indices: 答案中被引用的来源序号（1-based）。
        invalid_reference_indices: 越界的来源序号（模型自造引用）。
        missing_reference: 答案中没有任何引用标记时为 ``True``。
    """

    total: int = 0
    valid: list[Citation] = field(default_factory=list)
    invalid: list[Citation] = field(default_factory=list)
    referenced_indices: list[int] = field(default_factory=list)
    invalid_reference_indices: list[int] = field(default_factory=list)
    missing_reference: bool = False

    @property
    def has_fabricated_references(self) -> bool:
        """``True`` 表示模型引用了不存在的来源编号。"""
        return bool(self.invalid_reference_indices)

    @property
    def is_consistent(self) -> bool:
        return not self.invalid and not self.invalid_reference_indices

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "valid": len(self.valid),
            "invalid": [c.to_dict() for c in self.invalid],
            "referenced_indices": self.referenced_indices,
            "invalid_reference_indices": self.invalid_reference_indices,
            "missing_reference": self.missing_reference,
            "is_consistent": self.is_consistent,
        }


def extract_reference_indices(answer: str) -> list[int]:
    """Return the source numbers referenced in *answer* (deduplicated, sorted)."""
    if not answer:
        return []
    return sorted({int(m) for m in REFERENCE_PATTERN.findall(answer)})


def validate_citations(
    citations: Iterable[Citation],
    context_chunks: Iterable[dict[str, Any]],
    answer: Optional[str] = None,
) -> CitationValidation:
    """校验引用是否与本次上下文一致，并检查答案里的 ``[来源N]`` 是否越界。"""
    citation_list = list(citations)
    chunk_list = list(context_chunks)

    available = {
        (str(chunk.get("document_id", "")), int(chunk.get("chunk_index", -1)))
        for chunk in chunk_list
    }

    result = CitationValidation(total=len(citation_list))
    for citation in citation_list:
        key = (str(citation.document_id), int(citation.chunk_id))
        if key in available:
            result.valid.append(citation)
        else:
            result.invalid.append(citation)

    if answer is not None:
        indices = extract_reference_indices(answer)
        result.referenced_indices = indices
        result.missing_reference = not indices
        upper_bound = len(chunk_list)
        result.invalid_reference_indices = [i for i in indices if i < 1 or i > upper_bound]

    if not result.is_consistent:
        logger.warning(
            f"引用一致性校验未通过: invalid_citations={len(result.invalid)}, "
            f"out_of_range_refs={result.invalid_reference_indices}"
        )
    return result


async def documents_exist(
    db: AsyncSession,
    document_ids: Iterable[str],
) -> set[str]:
    """Return the subset of *document_ids* that still exist in the database.

    用于"文档删除后引用不应指向不存在的数据"（§5.5）。
    """
    from ...models.document import Document

    ids = {d for d in document_ids if d}
    if not ids:
        return set()

    result = await db.execute(
        select(Document.id).where(Document.id.in_(list(ids)))
    )
    return {row[0] for row in result.all()}


async def filter_live_citations(
    db: AsyncSession,
    citations: Iterable[Citation],
) -> list[Citation]:
    """Drop citations whose document no longer exists（文档已删除）。"""
    citation_list = list(citations)
    if not citation_list:
        return []

    alive = await documents_exist(db, (c.document_id for c in citation_list))
    live = [c for c in citation_list if c.document_id in alive]

    if len(live) != len(citation_list):
        logger.info(
            f"过滤失效引用: {len(citation_list) - len(live)} 条引用的文档已被删除"
        )
    return live
