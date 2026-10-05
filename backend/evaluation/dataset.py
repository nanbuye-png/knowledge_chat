"""评测数据集与语料加载 + 真实性校验。

为什么需要"校验"
----------------
评测集最大的风险不是指标算错，而是**标注本身是错的**：
写出一个语料里根本不存在的"标准答案"，指标就会奖励错误行为。
因此本模块把标注变成可执行约束：

* ``answerable=true`` 的题目：``evidence_keywords`` 至少要有一条**真的出现在语料原文中**；
* ``answerable=false`` 的题目：``probe_terms`` **必须完全不出现**在任何语料中；
* 语料清单中 ``verify_hash=true`` 的文件：sha256 必须一致（防止语料被无意改动后指标失真）。

校验失败会返回问题列表（而不是抛异常），由 CLI 打印、由 pytest 断言必须为空。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_PATH = EVALUATION_DIR / "datasets" / "rag_eval_v1.json"
DEFAULT_MANIFEST_PATH = EVALUATION_DIR / "corpus" / "manifest.json"

VALID_CATEGORIES = (
    "faq",
    "rag_pipeline",
    "commerce",
    "engineering",
    "handbook",
    "cross_doc",
    "no_answer",
)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class EvaluationItem:
    """单条评测题。"""

    id: str
    question: str
    category: str
    answerable: bool
    reference_answer: str = ""
    evidence_keywords: list[str] = field(default_factory=list)
    probe_terms: list[str] = field(default_factory=list)
    gold_docs: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def is_no_answer(self) -> bool:
        return not self.answerable

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "answerable": self.answerable,
            "question": self.question,
            "reference_answer": self.reference_answer,
            "evidence_keywords": list(self.evidence_keywords),
            "probe_terms": list(self.probe_terms),
            "gold_docs": list(self.gold_docs),
        }


@dataclass
class EvaluationDataset:
    """评测集（题目列表 + 元信息）。"""

    version: str
    items: list[EvaluationItem]
    path: Optional[Path] = None
    description: str = ""

    @property
    def answerable_items(self) -> list[EvaluationItem]:
        return [i for i in self.items if i.answerable]

    @property
    def no_answer_items(self) -> list[EvaluationItem]:
        return [i for i in self.items if not i.answerable]

    def by_id(self, item_id: str) -> Optional[EvaluationItem]:
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.category] = counts.get(item.category, 0) + 1
        return dict(sorted(counts.items()))


@dataclass
class CorpusDoc:
    """评测语料中的一篇文档。"""

    name: str
    path: Path
    text: str
    role: str = "primary"
    origin: str = ""
    sha256: str = ""
    expected_sha256: str = ""
    verify_hash: bool = False
    #: 可选语料：仓库不跟踪 / 只在某些环境存在的干扰项，缺席时跳过而不是判为损坏
    optional: bool = False

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def contains(self, term: str) -> bool:
        return bool(term) and term in self.text

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "role": self.role,
            "chars": len(self.text),
            "sha256": self.sha256,
        }



# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sha256_of(path: Path) -> str:
    """语料指纹（先按 LF 归一化，再算 sha256）。

    为什么不是直接对字节做 sha256：文本语料在 Windows 上检出会带 CRLF
    （``core.autocrlf=true``），CI 在 Linux 上是 LF —— 同一份语料会得出两个
    哈希，校验和就退化成"和操作系统绑定"的假约束（实测 CI 上
    ``wuxi_culture_palace_faq.txt`` 因此被报成"语料内容已变化"）。
    归一化只忽略行尾风格，正文任何改动仍然会被抓到。
    """
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def load_dataset(path: Path | str | None = None) -> EvaluationDataset:
    """Load the evaluation dataset from *path* (default: ``rag_eval_v1.json``)."""
    dataset_path = Path(path) if path else DEFAULT_DATASET_PATH
    raw = json.loads(_read_text(dataset_path))

    items = [
        EvaluationItem(
            id=entry["id"],
            question=entry["question"],
            category=entry.get("category", "unknown"),
            answerable=bool(entry.get("answerable", True)),
            reference_answer=entry.get("reference_answer", ""),
            evidence_keywords=list(entry.get("evidence_keywords", []) or []),
            probe_terms=list(entry.get("probe_terms", []) or []),
            gold_docs=list(entry.get("gold_docs", []) or []),
            note=entry.get("note", ""),
        )
        for entry in raw.get("items", [])
    ]

    return EvaluationDataset(
        version=str(raw.get("version", "0")),
        items=items,
        path=dataset_path,
        description=raw.get("description", ""),
    )


def load_manifest(path: Path | str | None = None) -> dict[str, Any]:
    """Load the corpus manifest (raw JSON)."""
    manifest_path = Path(path) if path else DEFAULT_MANIFEST_PATH
    return json.loads(_read_text(manifest_path))


def load_corpus(path: Path | str | None = None) -> list[CorpusDoc]:
    """Load every corpus document, reading text into memory.

    Missing **required** files are returned with ``text=""`` so that
    :func:`validate_dataset` can report them as problems instead of raising.
    Entries marked ``optional`` (e.g. a distractor that is ``.gitignore``-d and
    only exists on some machines) are skipped instead of being reported as
    "语料文件不存在" —— CI 上没有它就判数据集损坏，属于把本地文件当仓库文件。
    """
    manifest_path = Path(path) if path else DEFAULT_MANIFEST_PATH
    manifest = load_manifest(manifest_path)
    base = EVALUATION_DIR

    docs: list[CorpusDoc] = []
    for entry in manifest.get("docs", []):
        resolved = (base / entry["path"]).resolve()
        optional = bool(entry.get("optional", False))
        if optional and not resolved.is_file():
            continue
        text = _read_text(resolved) if resolved.is_file() else ""
        actual = sha256_of(resolved) if resolved.is_file() else ""
        docs.append(
            CorpusDoc(
                name=entry["name"],
                path=resolved,
                text=text,
                role=entry.get("role", "primary"),
                origin=entry.get("origin", ""),
                sha256=actual,
                expected_sha256=entry.get("sha256", ""),
                verify_hash=bool(entry.get("verify_hash", False)),
                optional=optional,
            )
        )
    return docs


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def validate_dataset(
    dataset: EvaluationDataset,
    corpus: list[CorpusDoc],
) -> list[str]:
    """Return a list of problems; an empty list means the dataset is sound."""
    problems: list[str] = []

    if not dataset.items:
        problems.append("数据集为空：没有任何评测题")
        return problems

    # ---- 语料 ----
    if not corpus:
        problems.append("语料为空：manifest 中没有文档")
    for doc in corpus:
        if not doc.exists:
            problems.append(f"语料文件不存在: {doc.name} -> {doc.path}")
            continue
        if len(doc.text.strip()) < 50:
            problems.append(f"语料内容过短（可能为空文件）: {doc.name}")
        if doc.verify_hash and doc.expected_sha256 and doc.sha256 != doc.expected_sha256:
            problems.append(
                f"语料校验和不一致: {doc.name} "
                f"(expect {doc.expected_sha256[:12]}..., got {doc.sha256[:12]}...)"
            )

    # ---- 题目 ----
    seen: set[str] = set()
    for item in dataset.items:
        label = item.id or "<no-id>"

        if not item.id:
            problems.append("存在缺少 id 的评测题")
        elif item.id in seen:
            problems.append(f"{label}: id 重复")
        seen.add(item.id)

        if not item.question.strip():
            problems.append(f"{label}: question 为空")
        if item.category not in VALID_CATEGORIES:
            problems.append(f"{label}: 非法 category '{item.category}'")

        if item.answerable:
            if not item.reference_answer.strip():
                problems.append(f"{label}: answerable 题目缺少 reference_answer")
            if not item.evidence_keywords:
                problems.append(f"{label}: answerable 题目缺少 evidence_keywords")
            for kw in item.evidence_keywords:
                where = [d.name for d in corpus if d.contains(kw)]
                if not where:
                    problems.append(
                        f"{label}: evidence_keyword '{kw}' 未出现在任何语料文件中（可疑标注）"
                    )
            known = {d.name for d in corpus}
            for doc_name in item.gold_docs:
                if doc_name not in known:
                    problems.append(f"{label}: gold_docs 引用了未知文件 {doc_name}")
        else:
            if not item.probe_terms:
                problems.append(f"{label}: no_answer 题目缺少 probe_terms")
            for term in item.probe_terms:
                where = [d.name for d in corpus if d.contains(term)]
                if where:
                    problems.append(
                        f"{label}: 期望无答案，但 probe_term '{term}' 出现在语料 {where} 中 "
                        "—— 该题实际可答或探针词选错"
                    )

    return problems


def corpus_summary(corpus: list[CorpusDoc]) -> dict[str, Any]:
    """Aggregate statistics about the evaluation corpus."""
    return {
        "documents": len(corpus),
        "chars": sum(len(d.text) for d in corpus),
        "roles": {
            role: sum(1 for d in corpus if d.role == role)
            for role in sorted({d.role for d in corpus})
        },
        "docs": [d.to_dict() for d in corpus],
    }

