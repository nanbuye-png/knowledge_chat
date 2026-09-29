"""RAG 评测运行器（CLI）。

一次运行做什么
--------------
```text
1. 隔离工作区：把 DB / Chroma / 稀疏索引 / 上传目录全部指向临时目录
   （在 import 应用模块之前设置环境变量，见 _configure_environment）
2. 建库：创建临时 SQLite schema，插入一个评测用户与知识库
3. 入库：用生产同一套 KnowledgePipeline 处理语料（真实解析/切分/向量化/BM25）
4. 逐题评测：
   4.1 RetrievalPipeline.retrieve() ── 记录最终上下文 chunk 与分数（检索指标）
   4.2 ChatService.query_knowledge() ── **生产问答入口**（拒答/生成/引用）
   4.3 LLMJudge ── 正确性 / 忠实度 / 幻觉（可选）
5. 汇总：检索指标、拒答指标、生成指标、引用校验、阈值扫描，全部写入 JSON
```

纪律
----
* 评测语料与数据集必须先通过 :func:`evaluation.dataset.validate_dataset`，
  否则直接失败（避免用可疑标注产出"漂亮"指标）。
* 阈值扫描复用本次 trace，不需要重复调用模型。
* ``--no-llm`` 只跑检索链路：零成本、可离线复现，用于回归。

用法::

    cd backend
    python -m evaluation.runner --validate-only
    python -m evaluation.runner --no-llm --mode hybrid
    python -m evaluation.runner --mode hybrid --out evaluation/reports/hybrid.json
    python -m evaluation.runner --mode vector --out evaluation/reports/vector.json
    # 裁判被限流（429）丢分时：只补裁判，不重跑检索/生成
    python -m evaluation.runner --rejudge evaluation/reports/hybrid.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from . import metrics as M
from .dataset import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MANIFEST_PATH,
    EvaluationDataset,
    EvaluationItem,
    corpus_summary,
    load_corpus,
    load_dataset,
    validate_dataset,
)
from .judge import LLMJudge, MAX_CONTEXT_CHARS, create_judge

EVALUATION_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT_DIR = EVALUATION_DIR / "reports"

#: 记录每个 chunk 文本的截断长度（控制 JSON 体积）
CHUNK_TEXT_LIMIT = 300


@dataclass
class RunConfig:
    """Everything needed to reproduce one evaluation run."""

    mode: str = "hybrid"
    dataset_path: Path = DEFAULT_DATASET_PATH
    manifest_path: Path = DEFAULT_MANIFEST_PATH
    limit: Optional[int] = None
    use_llm: bool = True
    workspace: Optional[Path] = None
    keep_workspace: bool = False
    query_rewrite: bool = False
    judge_max_tokens: int = 800
    judge_retry: int = 4
    judge_retry_delay: float = 3.0
    output: Optional[Path] = None
    tag: str = ""
    verbose: bool = False
    allow_download: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "dataset": str(self.dataset_path),
            "manifest": str(self.manifest_path),
            "limit": self.limit,
            "use_llm": self.use_llm,
            "query_rewrite": self.query_rewrite,
            "judge_max_tokens": self.judge_max_tokens,
            "judge_retry": self.judge_retry,
            "judge_retry_delay": self.judge_retry_delay,
            "tag": self.tag,
            "offline_model": not self.allow_download,
        }


# ---------------------------------------------------------------------------
# 环境隔离（必须在 import app.* 之前调用）
# ---------------------------------------------------------------------------


def _configure_environment(cfg: RunConfig) -> dict[str, str]:
    """Point every piece of state at a throwaway workspace.

    ``app.core.config`` reads environment variables with priority over
    ``.env``, and every stateful singleton (SQLAlchemy engine, Chroma
    client, BM25 index) resolves its path lazily on first use.  Setting the
    variables here — before importing any ``app.*`` module — therefore gives
    the run a fully isolated database, vector store and sparse index, and
    leaves the developer's real data untouched.
    """
    workspace = cfg.workspace or Path(tempfile.mkdtemp(prefix="rag_eval_"))
    workspace = Path(workspace).resolve()
    (workspace / "uploads").mkdir(parents=True, exist_ok=True)
    (workspace / "chroma").mkdir(parents=True, exist_ok=True)

    env = {
        "DATABASE_URL": f"sqlite+aiosqlite:///{(workspace / 'eval.db').as_posix()}",
        "CHROMA_PERSIST_DIR": (workspace / "chroma").as_posix(),
        "SPARSE_INDEX_PATH": (workspace / "sparse_index.db").as_posix(),
        "UPLOAD_DIR": (workspace / "uploads").as_posix(),
        "RETRIEVAL_MODE": cfg.mode,
        "QUERY_REWRITE_ENABLED": "true" if cfg.query_rewrite else "false",
        "DOCUMENT_PROCESSING_ASYNC": "false",
        "LOG_LEVEL": "INFO" if cfg.verbose else "WARNING",
    }
    if not cfg.allow_download:
        # 评测必须与网络解耦：SentenceTransformer(model) 会向 HF Hub（此处是 hf-mirror
        # 镜像）查询模型元数据，镜像不可达时会长时间挂起，随后抛
        # "Cannot send a request, as the client has been closed"。
        # 本地缓存已存在时强制离线，模型加载变成纯本地操作、结果可复现。
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.update(env)
    env["workspace"] = str(workspace)
    return env


def _load_app_stack() -> dict[str, Any]:
    """Import the application modules used by the runner (after env setup)."""
    from app.core.config import settings
    from app.models.document import Base, Document, DocumentStatus
    from app.models.knowledge_base import KnowledgeBase
    from app.models.user import User
    from app.services.chat_service import chat_service
    from app.services.citation.models import Citation
    from app.services.citation.validator import validate_citations
    from app.services.embedding_service import embedding_service
    from app.services.knowledge.context import KnowledgePipelineContext
    from app.services.knowledge.pipeline import KnowledgePipeline
    from app.services.retrieval.abstention import create_abstention_decider
    from app.services.retrieval_pipeline import RetrievalPipeline
    from app.storage.database import async_session, engine
    from app.storage.vector_store import vector_store

    return {
        "settings": settings,
        "Base": Base,
        "Document": Document,
        "DocumentStatus": DocumentStatus,
        "KnowledgeBase": KnowledgeBase,
        "User": User,
        "chat_service": chat_service,
        "Citation": Citation,
        "validate_citations": validate_citations,
        "embedding_service": embedding_service,
        "KnowledgePipelineContext": KnowledgePipelineContext,
        "KnowledgePipeline": KnowledgePipeline,
        "create_abstention_decider": create_abstention_decider,
        "RetrievalPipeline": RetrievalPipeline,
        "async_session": async_session,
        "engine": engine,
        "vector_store": vector_store,
    }



# ---------------------------------------------------------------------------
# 建库 + 入库
# ---------------------------------------------------------------------------


async def _create_schema(app: dict[str, Any]) -> None:
    async with app["engine"].begin() as conn:
        await conn.run_sync(app["Base"].metadata.create_all)


async def _seed_knowledge_base(app: dict[str, Any], name: str) -> int:
    """Create an evaluation user + knowledge base, returning the KB id."""
    User = app["User"]
    KnowledgeBase = app["KnowledgeBase"]

    async with app["async_session"]() as session:
        user = User(
            username="eval_runner",
            email="eval_runner@example.invalid",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.flush()
        kb = KnowledgeBase(
            user_id=user.id, name=name, description="RAG evaluation corpus"
        )
        session.add(kb)
        await session.flush()
        kb_id = int(kb.id)
        await session.commit()
    logger.info(f"评测知识库已创建: kb_id={kb_id}")
    return kb_id


async def _ingest_corpus(
    app: dict[str, Any],
    corpus: list[Any],
    kb_id: int,
    upload_dir: Path,
) -> list[dict[str, Any]]:
    """Run every corpus document through the production ingestion pipeline."""
    Document = app["Document"]
    DocumentStatus = app["DocumentStatus"]
    pipeline = app["KnowledgePipeline"]()

    results: list[dict[str, Any]] = []
    for doc in corpus:
        target = upload_dir / doc.name
        shutil.copyfile(doc.path, target)
        document_id = str(uuid.uuid4())
        started = time.monotonic()

        async with app["async_session"]() as session:
            row = Document(
                id=document_id,
                filename=doc.name,
                file_size=target.stat().st_size,
                file_type=target.suffix.lstrip("."),
                status=DocumentStatus.PROCESSING.value,
                knowledge_base_id=kb_id,
            )
            session.add(row)
            await session.commit()

        context = app["KnowledgePipelineContext"](
            file_path=str(target),
            document_id=document_id,
            filename=doc.name,
            knowledge_base_id=kb_id,
        )
        status = DocumentStatus.COMPLETED.value
        error_message = None
        chunks = 0
        try:
            chunks = await pipeline.process_document(context)
        except Exception as exc:  # noqa: BLE001 - 入库失败要记录而不是中断评测
            status = DocumentStatus.FAILED.value
            error_message = str(exc)[:1000]
            logger.error(f"入库失败 {doc.name}: {exc}")

        async with app["async_session"]() as session:
            stored = await session.get(Document, document_id)
            if stored is not None:
                stored.status = status
                stored.chunk_count = chunks
                stored.error_message = error_message
                await session.commit()

        results.append(
            {
                "document_id": document_id,
                "filename": doc.name,
                "role": doc.role,
                "chars": len(doc.text),
                "chunks": chunks,
                "status": status,
                "error_message": error_message,
                "seconds": round(time.monotonic() - started, 2),
            }
        )
        logger.info(f"入库完成 {doc.name}: {chunks} chunks ({status})")

    return results


# ---------------------------------------------------------------------------
# 单题评测
# ---------------------------------------------------------------------------


def _chunk_trace(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": chunk.get("document_id"),
        "filename": chunk.get("filename"),
        "chunk_index": chunk.get("chunk_index"),
        "page": chunk.get("page"),
        "section": chunk.get("section"),
        "score": round(float(chunk.get("score") or 0.0), 6),
        "rerank_score": (
            round(float(chunk["rerank_score"]), 6)
            if chunk.get("rerank_score") is not None
            else None
        ),
        "text": str(chunk.get("text") or "")[:CHUNK_TEXT_LIMIT],
    }


def _context_text(chunks: list[dict[str, Any]]) -> str:
    """把最终上下文拼成裁判可读文本（与生产 RAG Prompt 的拼法一致）。"""
    return "\n\n".join(str(c.get("text") or "") for c in chunks)


def _context_signature(chunks: list[dict[str, Any]]) -> list[list[Any]]:
    """上下文的稳定指纹：``(filename, chunk_index)`` 序列。

    补判时可用来验证"重算出的上下文"与"原报告记录的上下文"是同一批 chunk。
    **不能用 document_id**：每次重新入库都会生成新的文档 UUID，
    用它做指纹会导致\"一律不一致\"的假告警（实测踩过）。
    """
    return [[c.get("filename"), c.get("chunk_index")] for c in chunks]


def _needs_rejudge(record: dict[str, Any]) -> bool:
    """已作答、但缺裁判结果或裁判失败的记录。"""
    if not record.get("answered"):
        return False
    judgement = record.get("judgement") or {}
    return not judgement or bool(judgement.get("judge_error"))


def _citation_summary(
    app: dict[str, Any],
    response: Any,
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rebuild :class:`Citation` objects and run the production validator."""
    Citation = app["Citation"]
    citations = [
        Citation(
            document_id=str(c.get("document_id", "")),
            filename=str(c.get("filename", "")),
            chunk_id=int(c.get("chunk_id", -1)),
            score=float(c.get("score") or 0.0),
            page=c.get("page"),
            section=c.get("section"),
        )
        for c in (response.citations or [])
    ]
    validation = app["validate_citations"](
        citations, chunks, answer=response.answer or ""
    )
    located = sum(1 for c in citations if c.page is not None or c.section is not None)
    return {
        "count": len(citations),
        "located": located,
        "valid": len(validation.valid),
        "invalid": len(validation.invalid),
        "referenced_indices": validation.referenced_indices,
        "invalid_reference_indices": validation.invalid_reference_indices,
        "is_consistent": validation.is_consistent,
        "has_reference_marker": not validation.missing_reference,
    }


async def _apply_response(
    app: dict[str, Any],
    record: dict[str, Any],
    response: Any,
    pipeline: Any,
    kb_id: int,
    context: Optional[str] = None,
) -> None:
    """把一次生产问答响应写回记录（生成 / 引用 / 来源 / 上下文）。

    集中在这里是为了让"完整评测"与"--regenerate 重跑失败题"用同一套口径，
    避免两处手写字段导致长期漂移。
    """
    answer = response.answer or ""
    chunks = [dict(c) for c in (record.get("chunks") or [])]
    record.update(
        {
            "answer": answer,
            "answered": not bool(getattr(response, "abstained", False)),
            "abstained": bool(getattr(response, "abstained", False)),
            "abstention_reason_response": getattr(response, "abstention_reason", None),
            "has_knowledge": bool(getattr(response, "has_knowledge", False)),
            "answer_chars": len(answer),
            "empty_answer": not answer.strip(),
            # 系统故障（LLM 限流/超时）：与"拒答"必须区分，指标里单独统计
            "generation_error": getattr(response, "error", None),
            "citations": _citation_summary(app, response, chunks),
            "sources": [
                {
                    "filename": s.filename,
                    "chunk_index": s.chunk_index,
                    "page": s.page,
                    "section": s.section,
                }
                for s in (getattr(response, "sources", None) or [])
            ],
        }
    )
    record["has_citation"] = record["citations"]["has_reference_marker"]
    record["abstention_matches"] = bool(record["abstained"]) == bool(
        record.get("abstained_decision")
    )

    if context is not None:
        record["context_text"] = context[:MAX_CONTEXT_CHARS]
    elif not record.get("context_text"):
        # 供 --rejudge 离线复算：把裁判实际看到的上下文落盘
        result = await pipeline.retrieve(
            question=record["question"], knowledge_base_id=kb_id
        )
        record["context_text"] = _context_text(list(result.results or []))[
            :MAX_CONTEXT_CHARS
        ]


async def _evaluate_item(
    item: EvaluationItem,
    kb_id: int,
    app: dict[str, Any],
    pipeline: Any,
    decider: Any,
    judge: Optional[LLMJudge],
    use_llm: bool,
    index: int,
    total: int,
) -> dict[str, Any]:
    """Evaluate one question through retrieval and (optionally) generation."""
    started = time.monotonic()
    # 三阶段可归因检索（全部为本地计算，不产生 LLM 成本）：
    # ① 召回池（top_k=20, min_score=0）——排序/召回质量
    pool_result = await pipeline.retrieve(
        question=item.question, knowledge_base_id=kb_id, top_k=20, min_score=0.0
    )
    pool_chunks = list(pool_result.results or [])
    # ② 无分数过滤的 rerank 结果（生产 top_k=5）——衡量 Reranker 的效果
    unfiltered_result = await pipeline.retrieve(
        question=item.question, knowledge_base_id=kb_id, min_score=0.0
    )
    unfiltered = list(unfiltered_result.results or [])
    # ③ 生产配置（含 RETRIEVAL_MIN_SCORE 过滤）——真正进入 LLM 的上下文与拒答判定
    result = await pipeline.retrieve(question=item.question, knowledge_base_id=kb_id)
    chunks = list(result.results or [])
    retrieval_ms = (time.monotonic() - started) * 1000

    decision = decider.decide(result)
    best_score = max((float(c.get("score") or 0.0) for c in unfiltered), default=0.0)
    context_best = max((float(c.get("score") or 0.0) for c in chunks), default=0.0)
    rerank_scores = [
        float(c["rerank_score"]) for c in chunks if c.get("rerank_score") is not None
    ]

    record: dict[str, Any] = {
        "index": index,
        "id": item.id,
        "category": item.category,
        "answerable": item.answerable,
        "question": item.question,
        "reference_answer": item.reference_answer,
        "retrieved": len(chunks),
        "unfiltered_count": len(unfiltered),
        "pool_count": len(pool_chunks),
        "has_results": bool(result.has_results),
        "best_score": round(best_score, 6),
        "context_best_score": round(context_best, 6),
        "best_rerank": round(max(rerank_scores), 6) if rerank_scores else None,
        "rewrite_status": result.rewrite_status,
        "search_query": result.search_query,
        "abstained_decision": decision.should_abstain,
        "abstention_reason": decision.reason,
        "abstention_details": decision.details,
        "retrieval_ms": round(retrieval_ms, 1),
        "chunks": [_chunk_trace(c) for c in chunks],
        "unfiltered_chunks": [_chunk_trace(c) for c in unfiltered],
        "pool_chunks": [_chunk_trace(c) for c in pool_chunks],
    }

    if item.answerable:
        for key, source in (
            ("retrieval_pool", pool_chunks),
            ("retrieval", unfiltered),
            ("retrieval_production", chunks),
        ):
            record[key] = M.evaluate_item_retrieval(
                item_id=item.id,
                category=item.category,
                chunks=source,
                keywords=item.evidence_keywords,
                gold_docs=item.gold_docs,
            ).to_dict()

    # 默认拒答判定取检索侧决策；LLM 路径开启后以生产响应为准
    record["abstained"] = decision.should_abstain

    if use_llm:
        response = await app["chat_service"].query_knowledge(
            question=item.question,
            knowledge_base_id=kb_id,
        )
        await _apply_response(
            app,
            record,
            response,
            pipeline,
            kb_id,
            context=_context_text(chunks),
        )

        if not response.abstained and judge is not None:
            judgement = await judge.judge(
                item_id=item.id,
                question=item.question,
                reference_answer=item.reference_answer,
                answer=record.get("answer") or "",
                context=record.get("context_text") or "",
            )
            record["judgement"] = judgement.to_dict()

    logger.info(
        f"[{index}/{total}] {item.id} retrieved={len(chunks)} "
        f"abstained={record['abstained']}"
    )
    return record


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def _pipeline_config_snapshot(settings: Any) -> dict[str, Any]:
    """Record every knob that could change the measured numbers."""
    keys = (
        "RETRIEVAL_MODE",
        "HYBRID_VECTOR_WEIGHT",
        "HYBRID_BM25_WEIGHT",
        "HYBRID_RECALL_K",
        "SPARSE_BM25_K1",
        "SPARSE_BM25_B",
        "SPARSE_INDEX_FALLBACK",
        "RERANKER_ENABLED",
        "RERANKER_TYPE",
        "RERANKER_MODEL",
        "RERANKER_CANDIDATES",
        "RERANKER_TOP_K",
        "RERANKER_TIMEOUT",
        "CONTEXT_SCORE_THRESHOLD",
        "CONTEXT_SCORE_SOURCE",
        "ABSTENTION_ENABLED",
        "ABSTENTION_MIN_CONTEXT_CHUNKS",
        "ABSTENTION_SCORE_THRESHOLD",
        "ABSTENTION_RERANK_THRESHOLD",
        "QUERY_REWRITE_ENABLED",
        "CHUNK_SIZE",
        "CHUNK_OVERLAP",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIM",
        "LLM_PROVIDER",
        "LLM_MODEL",
    )
    return {key: getattr(settings, key, None) for key in keys}


def _mean_len(records: list[dict[str, Any]], key: str) -> float:
    """Average of an integer field across records (0.0 when no records)."""
    values = [float(r.get(key) or 0) for r in records]
    return sum(values) / len(values) if values else 0.0


def _citation_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    answered = [r for r in records if r.get("answer") is not None and not r.get("abstained")]
    with_citations = [r for r in answered if r.get("citations", {}).get("count")]
    consistent = [r for r in with_citations if r["citations"]["is_consistent"]]
    fabricated = [r for r in with_citations if r["citations"]["invalid_reference_indices"]]
    total_citations = sum(r["citations"]["count"] for r in with_citations)
    located = sum(r["citations"]["located"] for r in with_citations)
    return {
        "answered_items": len(answered),
        "items_with_citations": len(with_citations),
        "citation_rate": len(with_citations) / len(answered) if answered else 0.0,
        "consistent_items": len(consistent),
        "consistency_rate": len(consistent) / len(with_citations) if with_citations else 0.0,
        "items_with_fabricated_reference": len(fabricated),
        "fabricated_reference_rate": len(fabricated) / len(with_citations) if with_citations else 0.0,
        "total_citations": total_citations,
        "located_citations": located,
        "locator_coverage": located / total_citations if total_citations else 0.0,
        "reference_marker_items": sum(1 for r in answered if r.get("has_citation")),
    }


def _build_payload(
    cfg: RunConfig,
    env: dict[str, str],
    dataset: EvaluationDataset,
    corpus: list[Any],
    ingestion: list[dict[str, Any]],
    records: list[dict[str, Any]],
    settings: Any,
    judge: Optional[LLMJudge],
    started_at: datetime,
    duration: float,
) -> dict[str, Any]:
    retrieval_items = [
        M.ItemRetrievalResult(**r["retrieval"]) for r in records if "retrieval" in r
    ]
    pool_items = [
        M.ItemRetrievalResult(**r["retrieval_pool"])
        for r in records
        if "retrieval_pool" in r
    ]
    production_items = [
        M.ItemRetrievalResult(**r["retrieval_production"])
        for r in records
        if "retrieval_production" in r
    ]
    llm_items = [r for r in records if "answer" in r]
    return {
        "schema_version": 1,
        "run": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration, 1),
            "config": cfg.to_dict(),
            "workspace": env.get("workspace"),
            "pipeline_config": _pipeline_config_snapshot(settings),
            "judge_model": judge.model if judge else None,
            "dataset": {
                "path": str(dataset.path),
                "version": dataset.version,
                "items": len(records),
                "answerable": sum(1 for r in records if r["answerable"]),
                "no_answer": sum(1 for r in records if not r["answerable"]),
                "categories": dataset.category_counts(),
            },
            "corpus": corpus_summary(corpus),
            "ingestion": ingestion,
            "llm_calls_expected": len(llm_items) + sum(1 for r in llm_items if "judgement" in r),
        },
        "retrieval": M.aggregate_retrieval(retrieval_items).to_dict(),
        "retrieval_pool": M.aggregate_retrieval(pool_items).to_dict(),
        "retrieval_production": M.aggregate_retrieval(production_items).to_dict(),
        "context_sizes": {
            "pool_mean": _mean_len(records, "pool_count"),
            "unfiltered_mean": _mean_len(records, "unfiltered_count"),
            "production_mean": _mean_len(records, "retrieved"),
            "items_filtered_below_top5": sum(
                1 for r in records if r.get("retrieved", 0) < 5
            ),
        },
        "abstention": M.abstention_stats(records).to_dict(),
        "generation": M.generation_stats(records).to_dict(),
        "citations": _citation_stats(records),
        "consistency": {
            "llm_items": len(llm_items),
            "abstention_matches": sum(1 for r in llm_items if r.get("abstention_matches")),
            "abstention_mismatches": [
                r["id"] for r in llm_items if r.get("abstention_matches") is False
            ],
        },
        "threshold_sweep": M.threshold_sweep(records),
        "problems": [],
        "items": records,
    }


# ---------------------------------------------------------------------------
# 运行
# ---------------------------------------------------------------------------


def validate_only(cfg: RunConfig) -> list[str]:
    """Validate dataset + corpus without touching the model or the network."""
    dataset = load_dataset(cfg.dataset_path)
    corpus = load_corpus(cfg.manifest_path)
    problems = validate_dataset(dataset, corpus)
    print(f"数据集: {dataset.path}")
    print(
        f"题量: {len(dataset.items)}（可答 {len(dataset.answerable_items)} / "
        f"不可答 {len(dataset.no_answer_items)}）"
    )
    print(f"分类: {dataset.category_counts()}")
    summary = corpus_summary(corpus)
    print(f"语料: {summary['documents']} 篇 / {summary['chars']} 字符 / 角色 {summary['roles']}")
    for doc in summary["docs"]:
        print(f"  - {doc['name']} ({doc['chars']} 字符, {doc['role']})")
    print(f"校验问题: {len(problems)}")
    for problem in problems:
        print(f"  ! {problem}")
    return problems


async def _run(cfg: RunConfig, env: dict[str, str]) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

    dataset = load_dataset(cfg.dataset_path)
    corpus = load_corpus(cfg.manifest_path)
    problems = validate_dataset(dataset, corpus)
    if problems:
        for problem in problems:
            logger.error(f"数据集校验失败: {problem}")
        raise SystemExit(
            f"评测集校验未通过（{len(problems)} 个问题），已中止以免产出不可信指标"
        )
    logger.info(
        f"评测集就绪: {len(dataset.items)} 题 / {len(corpus)} 篇语料"
    )

    app = _load_app_stack()
    settings = app["settings"]
    await _create_schema(app)
    # 先加载嵌入模型再初始化向量库：模型加载是"重且可能联网"的一步，
    # 放在最前面失败时能更快暴露（且与 lifespan 的意图一致）。
    await app["embedding_service"].initialize()
    await app["vector_store"].initialize()

    kb_id = await _seed_knowledge_base(app, f"RAG Eval Corpus ({cfg.mode})")
    ingestion = await _ingest_corpus(
        app, corpus, kb_id, Path(env["workspace"]) / "uploads"
    )
    total_chunks = sum(entry["chunks"] for entry in ingestion)
    logger.info(f"语料入库完成: {total_chunks} chunks")

    items = dataset.items[: cfg.limit] if cfg.limit else dataset.items
    pipeline = app["RetrievalPipeline"]()
    decider = app["create_abstention_decider"]()
    judge = (
        create_judge(
            settings,
            max_tokens=cfg.judge_max_tokens,
            retry=cfg.judge_retry,
            retry_base_delay=cfg.judge_retry_delay,
        )
        if cfg.use_llm
        else None
    )
    if judge is not None:
        logger.info(f"裁判模型: {judge.model}（重试上限 {judge.retry} 次）")

    records: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        record = await _evaluate_item(
            item=item,
            kb_id=kb_id,
            app=app,
            pipeline=pipeline,
            decider=decider,
            judge=judge,
            use_llm=cfg.use_llm,
            index=index,
            total=len(items),
        )
        records.append(record)

    payload = _build_payload(
        cfg=cfg,
        env=env,
        dataset=dataset,
        corpus=corpus,
        ingestion=ingestion,
        records=records,
        settings=settings,
        judge=judge,
        started_at=started_at,
        duration=time.monotonic() - t0,
    )
    return payload


async def rejudge_report(
    report_path: Path,
    cfg: RunConfig,
    judge: LLMJudge,
    payload: Optional[dict[str, Any]] = None,
    uploads_dir: Optional[Path] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """给已有报告补裁判，不重跑问答（限流丢分时的恢复手段）。

    裁判所需的上下文按以下优先级获取：

    1. 记录里的 ``context_text``（本次运行已落盘，最忠实）；
    2. 否则重建隔离工作区、用**生产链路重算**该题的上下文（并校验 chunk 指纹
       是否与原报告一致，不一致则记录 ``context_mismatch``）。

    返回 ``(payload, summary)``，``payload["generation"]`` 已按补判后的结果重算。
    """
    if payload is None:
        payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
    records = payload.get("items") or []
    if not records:
        raise SystemExit(f"报告中没有 items，无法补判: {report_path}")
    if not (payload.get("generation") or {}).get("evaluated"):
        raise SystemExit(
            "该报告没有生成指标（可能是 --no-llm 跑出来的），没有可补判的答案"
        )

    targets = [r for r in records if _needs_rejudge(r)]
    summary: dict[str, Any] = {
        "targets": len(targets),
        "recovered": 0,
        "still_failed": 0,
        "context_from_report": 0,
        "context_recomputed": 0,
        "context_mismatch": [],
    }
    if not targets:
        logger.info("没有需要补判的题目（裁判结果完整）")
        return payload, summary

    missing_context = [r for r in targets if not r.get("context_text")]
    pipeline = None
    kb_id: Optional[int] = None
    if missing_context:
        logger.info(
            f"{len(missing_context)} 题缺少落盘上下文，将重建工作区并按生产链路重算上下文"
        )
        app = _load_app_stack()
        await _create_schema(app)
        await app["embedding_service"].initialize()
        await app["vector_store"].initialize()
        corpus = load_corpus(cfg.manifest_path)
        kb_id = await _seed_knowledge_base(app, f"RAG Eval Corpus ({cfg.mode}) rejudge")
        ingestion = await _ingest_corpus(
            app,
            corpus,
            kb_id,
            uploads_dir or Path(tempfile.mkdtemp(prefix="rag_eval_rejudge_")),
        )
        logger.info(f"语料重新入库完成: {sum(e['chunks'] for e in ingestion)} chunks")
        pipeline = app["RetrievalPipeline"]()

    for index, record in enumerate(targets, start=1):
        stored_context = record.get("context_text")
        if stored_context:
            context = stored_context
            source = "report"
            summary["context_from_report"] += 1
        else:
            result = await pipeline.retrieve(
                question=record["question"], knowledge_base_id=kb_id
            )
            chunks = list(result.results or [])
            context = _context_text(chunks)[:MAX_CONTEXT_CHARS]
            source = "recomputed"
            summary["context_recomputed"] += 1
            if _context_signature(chunks) != _context_signature(record.get("chunks") or []):
                summary["context_mismatch"].append(record["id"])
                logger.warning(
                    f"上下文指纹不一致 item={record['id']}："
                    "重算结果与原报告记录不同，请以新上下文为准并复核"
                )

        judgement = await judge.judge(
            item_id=record["id"],
            question=record["question"],
            reference_answer=record.get("reference_answer") or "",
            answer=record.get("answer") or "",
            context=context,
        )
        record["judgement"] = judgement.to_dict()
        record["context_text"] = context
        record["rejudged_at"] = datetime.now(timezone.utc).isoformat()
        record["rejudge_context_source"] = source
        if judgement.judge_error:
            summary["still_failed"] += 1
        else:
            summary["recovered"] += 1
        logger.info(
            f"[rejudge {index}/{len(targets)}] {record['id']} "
            f"attempts={judgement.attempts} error={judgement.judge_error or '-'}"
        )

    _recompute_derived(payload)
    payload.setdefault("run", {}).setdefault("rejudge_history", []).append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "judge_model": judge.model,
            "judge_retry": judge.retry,
            **{k: v for k, v in summary.items() if k != "context_mismatch"},
            "context_mismatch": summary["context_mismatch"],
        }
    )
    return payload, summary


def refresh_sweep(
    payload: dict[str, Any], record_history: bool = True
) -> tuple[dict[str, Any], dict[str, Any]]:
    """只重算 ``threshold_sweep``，不重跑任何检索/生成（纯函数，可离线复算）。

    阈值扫描是 ``items`` 里 ``answerable`` / ``best_score`` / ``unfiltered_count``
    的纯函数，因此换个候选网格（例如从粗网格换成 0.00~0.95 步长 0.05）不需要
    重新调模型：直接拿历史报告复算即可，避免\"为了看一眼阈值曲线重跑 71 次 LLM\"。
    """
    records = payload.get("items") or []
    if not records:
        raise SystemExit("报告中没有 items，无法重算阈值扫描")
    rows = M.threshold_sweep(records)
    summary = {
        "thresholds": [row["threshold"] for row in rows],
        "best": max(rows, key=lambda row: row["balanced_accuracy"]),
    }
    payload["threshold_sweep"] = rows
    if record_history:
        payload.setdefault("run", {}).setdefault("sweep_refresh_history", []).append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "thresholds": summary["thresholds"],
                "note": "recomputed from items (pure function, no model calls)",
            }
        )
    return payload, summary


def _recompute_derived(payload: dict[str, Any]) -> None:
    """重算所有"由 items 派生"的指标（纯函数，不调用任何模型）。

    补判/重生成会改写 ``answer`` 与 ``judgement``，所以拒答、生成、引用、一致性、
    阈值扫描这些派生指标必须一起刷新——否则报告里会出现"新答案 + 旧指标"的错配。
    """
    records = payload.get("items") or []
    llm_items = [r for r in records if "answer" in r]
    payload["abstention"] = M.abstention_stats(records).to_dict()
    payload["generation"] = M.generation_stats(records).to_dict()
    payload["citations"] = _citation_stats(records)
    payload["consistency"] = {
        "llm_items": len(llm_items),
        "abstention_matches": sum(1 for r in llm_items if r.get("abstention_matches")),
        "abstention_mismatches": [
            r["id"] for r in llm_items if r.get("abstention_matches") is False
        ],
    }
    refresh_sweep(payload, record_history=False)


async def regenerate_report(
    report_path: Path,
    cfg: RunConfig,
    judge: LLMJudge,
    payload: Optional[dict[str, Any]] = None,
    uploads_dir: Optional[Path] = None,
    retry: int = 3,
    retry_delay: float = 5.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """重跑**失败的生成**（LLM 报错/限流），再重新裁判；其余题目原样保留。

    与 ``--rejudge`` 的分工：

    * ``--rejudge``    ：答案没问题、只是裁判失败 → 只补裁判；
    * ``--regenerate`` ：答案是错误文案（系统故障）→ 重新走生产问答入口拿答案再裁判。

    为什么不能沿用旧答案：错误文案不是模型输出，把它算进正确性等于
    "用系统故障冒充模型答错"。重跑时对瞬时错误重试，尽量拿到真实回答。
    """
    if payload is None:
        payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
    records = payload.get("items") or []
    if not records:
        raise SystemExit(f"报告中没有 items，无法重生成: {report_path}")

    targets = [r for r in records if M.is_generation_error(r)]
    summary: dict[str, Any] = {
        "targets": len(targets),
        "recovered": 0,
        "still_failed": 0,
        "retried": 0,
    }
    if not targets:
        logger.info("没有需要重生成的题目（不存在系统故障样本）")
        return payload, summary

    app = _load_app_stack()
    await _create_schema(app)
    await app["embedding_service"].initialize()
    await app["vector_store"].initialize()
    corpus = load_corpus(cfg.manifest_path)
    kb_id = await _seed_knowledge_base(app, f"RAG Eval Corpus ({cfg.mode}) regenerate")
    ingestion = await _ingest_corpus(
        app,
        corpus,
        kb_id,
        uploads_dir or Path(tempfile.mkdtemp(prefix="rag_eval_regen_")),
    )
    logger.info(f"语料重新入库完成: {sum(e['chunks'] for e in ingestion)} chunks")
    chat_service = app["chat_service"]
    pipeline = app["RetrievalPipeline"]()

    for index, record in enumerate(targets, start=1):
        response = None
        for attempt in range(1, max(1, retry) + 1):
            response = await chat_service.query_knowledge(
                question=record["question"], knowledge_base_id=kb_id
            )
            if not getattr(response, "error", None):
                break
            if attempt < retry:
                summary["retried"] += 1
                delay = retry_delay * attempt
                logger.warning(
                    f"生成失败 item={record['id']} attempt={attempt}/{retry}: "
                    f"{response.error} → {delay:.1f}s 后重试"
                )
                await asyncio.sleep(delay)
        await _apply_response(app, record, response, pipeline, kb_id)
        judgement = await judge.judge(
            item_id=record["id"],
            question=record["question"],
            reference_answer=record.get("reference_answer") or "",
            answer=record.get("answer") or "",
            context=record.get("context_text") or "",
        )
        record["judgement"] = judgement.to_dict()

        if record.get("generation_error"):
            summary["still_failed"] += 1
        else:
            summary["recovered"] += 1
        logger.info(
            f"[regenerate {index}/{len(targets)}] {record['id']} "
            f"error={record.get('generation_error') or '-'} "
            f"judge_error={judgement.judge_error or '-'}"
        )

    _recompute_derived(payload)
    payload.setdefault("run", {}).setdefault("regenerate_history", []).append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "judge_model": judge.model,
            "generation_retry": retry,
            "generation_retry_delay": retry_delay,
            **summary,
        }
    )
    return payload, summary


def _write_payload(payload: dict[str, Any], cfg: RunConfig) -> Path:
    if cfg.output:
        target = Path(cfg.output)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = f"_{cfg.tag}" if cfg.tag else ""
        target = DEFAULT_REPORT_DIR / f"{cfg.mode}{suffix}_{stamp}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


def _print_summary(payload: dict[str, Any]) -> None:
    run = payload["run"]
    retrieval = payload["retrieval"]
    abstention = payload["abstention"]
    generation = payload["generation"]
    print("-" * 68)
    print(f"模式: {run['pipeline_config']['RETRIEVAL_MODE']}  题量: {run['dataset']['items']}")
    print(f"耗时: {run['duration_seconds']}s  语料 chunks: {sum(e['chunks'] for e in run['ingestion'])}")
    print(
        "检索: "
        + "  ".join(f"{k}={v:.3f}" for k, v in sorted(retrieval["recall"].items()))
        + f"  mrr@10={retrieval['mrr_at_10']:.3f}  ndcg@5={retrieval['ndcg_at_5']:.3f}"
        + f"  ctx_precision@5={retrieval['context_precision_at_5']:.3f}"
    )
    print(
        f"拒答: 正确拒答率={abstention['abstention_recall']:.3f}  "
        f"漏拒答率={abstention['over_answer_rate']:.3f}  "
        f"误拒答率={abstention['false_abstention_rate']:.3f}  "
        f"均衡准确率={abstention['balanced_accuracy']:.3f}"
    )
    if generation["evaluated"]:
        print(
            f"生成: 已评={generation['evaluated']}  正确性={generation['correctness']:.3f}  "
            f"忠实度={generation['faithfulness']:.3f}  空回答={generation['empty_answers']}  "
            f"裁判失败={generation['judge_errors']}"
        )
    citations = payload["citations"]
    print(
        f"引用: 覆盖={citations['citation_rate']:.3f}  "
        f"一致性={citations['consistency_rate']:.3f}  "
        f"定位覆盖={citations['locator_coverage']:.3f}  "
        f"自造引用题数={citations['items_with_fabricated_reference']}"
    )
    print("-" * 68)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.runner",
        description="Knowledge Chat RAG 评测：检索指标 + 拒答指标 + 生成指标（真实 LLM 裁判）",
    )
    parser.add_argument(
        "--mode",
        default="hybrid",
        choices=("hybrid", "vector"),
        help="检索模式（vector 为基线对照）",
    )
    parser.add_argument("--dataset", default=None, help="评测集 JSON 路径")
    parser.add_argument("--manifest", default=None, help="语料清单 JSON 路径")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（冒烟用）")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="跳过生成指标（只跑检索链路，零成本、可离线复现）",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="只校验评测集与语料，不加载模型、不联网",
    )
    parser.add_argument("--query-rewrite", action="store_true", help="开启 Query Rewrite 做消融")
    parser.add_argument("--judge-max-tokens", type=int, default=800, help="裁判单次最大 token")
    parser.add_argument(
        "--judge-retry",
        type=int,
        default=4,
        help="裁判瞬时错误（429/5xx/超时）最大尝试次数",
    )
    parser.add_argument(
        "--judge-retry-delay",
        type=float,
        default=3.0,
        help="裁判重试基础退避秒数（指数退避，上限 30s）",
    )
    parser.add_argument(
        "--rejudge",
        default=None,
        metavar="REPORT_JSON",
        help="给已有报告补裁判（不重跑检索/生成），默认原地写回",
    )
    parser.add_argument(
        "--regenerate",
        default=None,
        metavar="REPORT_JSON",
        help="重跑报告里 LLM 报错（生成失败）的题目并重新裁判，默认原地写回",
    )
    parser.add_argument(
        "--generation-retry",
        type=int,
        default=3,
        help="重生成时对 LLM 瞬时错误（429/超时）的最大尝试次数",
    )
    parser.add_argument(
        "--generation-retry-delay",
        type=float,
        default=5.0,
        help="重生成时每次重试的间隔秒数（按尝试次数线性递增）",
    )
    parser.add_argument(
        "--refresh-sweep",
        default=None,
        metavar="REPORT_JSON",
        help="只重算报告里的阈值扫描（纯函数，不调用模型），默认原地写回",
    )
    parser.add_argument("--out", default=None, help="结果 JSON 输出路径")
    parser.add_argument("--workspace", default=None, help="临时工作区目录（默认系统临时目录）")
    parser.add_argument("--keep-workspace", action="store_true", help="保留临时工作区")
    parser.add_argument("--tag", default="", help="文件名标签")
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="允许访问 HuggingFace 下载/校验模型（默认离线，仅用本地缓存）",
    )
    parser.add_argument("--verbose", action="store_true", help="打印 INFO 级日志")
    parser.add_argument(
        "--fail-on-problems",
        action="store_true",
        help="数据集校验有问题时以非零状态码退出（CI 用）",
    )
    return parser


def _report_mode(path: Path) -> Optional[str]:
    """读已有报告里记录的检索模式（补判时要用同一模式重算上下文）。"""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    mode = ((payload.get("run") or {}).get("config") or {}).get("mode")
    return mode if mode in ("hybrid", "vector") else None


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    # 补判要用\"原报告记录的模式\"重算上下文，否则指纹必然对不上
    # 对已有报告做维护（补裁判/重生成/重算扫描）时，必须沿用原报告记录的检索模式，
    # 否则重算上下文/检索都会换模式，数字不可比。
    patch_path = args.rejudge or args.regenerate or args.refresh_sweep
    mode = (_report_mode(Path(patch_path)) or args.mode) if patch_path else args.mode

    cfg = RunConfig(
        mode=mode,
        dataset_path=Path(args.dataset) if args.dataset else DEFAULT_DATASET_PATH,
        manifest_path=Path(args.manifest) if args.manifest else DEFAULT_MANIFEST_PATH,
        limit=args.limit,
        use_llm=not args.no_llm,
        workspace=Path(args.workspace) if args.workspace else None,
        keep_workspace=args.keep_workspace,
        query_rewrite=args.query_rewrite,
        judge_max_tokens=args.judge_max_tokens,
        judge_retry=args.judge_retry,
        judge_retry_delay=args.judge_retry_delay,
        output=Path(args.out) if args.out else None,
        tag=args.tag,
        verbose=args.verbose,
        allow_download=args.allow_download,
    )

    # validate-only 不加载模型、不建临时工作区
    if args.validate_only:
        problems = validate_only(cfg)
        return 1 if (problems and args.fail_on_problems) else 0

    # 环境隔离必须发生在任何 app.* 导入之前
    env = _configure_environment(cfg)

    if args.refresh_sweep:
        path = Path(args.refresh_sweep)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload, summary = refresh_sweep(payload)
        cfg.output = cfg.output or path
        target = _write_payload(payload, cfg)
        best = summary["best"]
        print(
            f"阈值扫描已重算（{len(summary['thresholds'])} 个候选点）：\n"
            f"  推荐阈值={best['threshold']}  均衡准确率={best['balanced_accuracy']:.3f}  "
            f"正确拒答率={best['abstention_recall']:.3f}  "
            f"误拒答率={best['false_abstention_rate']:.3f}"
        )
        print(f"结果已写回: {target}")
        return 0

    if args.regenerate:
        path = Path(args.regenerate)
        cfg.output = cfg.output or path
        judge = create_judge(
            max_tokens=cfg.judge_max_tokens,
            retry=cfg.judge_retry,
            retry_base_delay=cfg.judge_retry_delay,
        )
        try:
            payload, summary = asyncio.run(
                regenerate_report(
                    report_path=path,
                    cfg=cfg,
                    judge=judge,
                    uploads_dir=Path(env["workspace"]) / "uploads",
                    retry=args.generation_retry,
                    retry_delay=args.generation_retry_delay,
                )
            )
        finally:
            if not cfg.keep_workspace:
                shutil.rmtree(env["workspace"], ignore_errors=True)
        target = _write_payload(payload, cfg)
        _print_summary(payload)
        print(
            f"重生成: 目标={summary['targets']}  恢复={summary['recovered']}  "
            f"仍失败={summary['still_failed']}  触发重试={summary['retried']}"
        )
        print(f"结果已写回: {target}")
        return 0

    if args.rejudge:
        report_path = Path(args.rejudge)
        cfg.output = cfg.output or report_path
        judge = create_judge(
            max_tokens=cfg.judge_max_tokens,
            retry=cfg.judge_retry,
            retry_base_delay=cfg.judge_retry_delay,
        )
        try:
            payload, summary = asyncio.run(
                rejudge_report(
                    report_path=report_path,
                    cfg=cfg,
                    judge=judge,
                    uploads_dir=Path(env["workspace"]) / "uploads",
                )
            )
        finally:
            if not cfg.keep_workspace:
                shutil.rmtree(env["workspace"], ignore_errors=True)
        target = _write_payload(payload, cfg)
        _print_summary(payload)
        print(
            f"补判: 目标={summary['targets']}  恢复={summary['recovered']}  "
            f"仍失败={summary['still_failed']}  "
            f"上下文取自报告={summary['context_from_report']}  "
            f"重算={summary['context_recomputed']}  "
            f"指纹不一致={len(summary['context_mismatch'])}"
        )
        print(f"结果已写回: {target}")
        return 0

    try:
        payload = asyncio.run(_run(cfg, env))
    finally:
        if not cfg.keep_workspace:
            shutil.rmtree(env["workspace"], ignore_errors=True)

    target = _write_payload(payload, cfg)
    _print_summary(payload)
    print(f"结果已写入: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


