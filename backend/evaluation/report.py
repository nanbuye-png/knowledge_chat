"""报告生成器 —— 把评测 JSON 渲染成 Markdown（数字全部来自真实运行结果）。

为什么用"生成"而不是"手写"
--------------------------
手写报告最容易出现"指标和跑出来的不一致"。这里所有表格都由 JSON 直接渲染，
`docs/RAG_EVALUATION.md` 由本模块产出，任何人可以一条命令重新生成同一份表格。

用法::

    cd backend
    python -m evaluation.report \
        --current evaluation/reports/hybrid.json \
        --baseline evaluation/reports/vector.json \
        --out ../docs/RAG_EVALUATION.md
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

EVALUATION_DIR = Path(__file__).resolve().parent

RETRIEVAL_METRIC_LABELS = (
    ("recall@1", "Recall@1"),
    ("recall@3", "Recall@3"),
    ("recall@5", "Recall@5"),
    ("recall@10", "Recall@10"),
    ("mrr_at_10", "MRR@10"),
    ("ndcg_at_5", "nDCG@5"),
    ("context_precision_at_5", "上下文精确率代理@5"),
    ("doc_hit_at_5", "文档级命中@5"),
)


def _pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _num(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.3f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _delta(current: Optional[float], baseline: Optional[float]) -> str:
    if current is None or baseline is None:
        return "—"
    diff = current - baseline
    if abs(diff) < 1e-9:
        return "0.0pp"
    sign = "+" if diff > 0 else "−"
    return f"{sign}{abs(diff) * 100:.1f}pp"


def _retrieval_table(current: dict[str, Any], baseline: Optional[dict[str, Any]]) -> str:
    cur_retrieval = current["retrieval"]
    base_retrieval = (baseline or {}).get("retrieval")
    rows: list[list[str]] = []
    for key, label in RETRIEVAL_METRIC_LABELS:
        cur_value = (
            cur_retrieval["recall"].get(key)
            if key.startswith("recall")
            else cur_retrieval.get(key)
        )
        base_value = None
        if base_retrieval:
            base_value = (
                base_retrieval["recall"].get(key)
                if key.startswith("recall")
                else base_retrieval.get(key)
            )
        rows.append(
            [
                label,
                _num(cur_value),
                _num(base_value) if base_retrieval else "—",
                _delta(cur_value, base_value) if base_retrieval else "—",
            ]
        )
    headers = ["指标", "Hybrid（当前）", "Vector（基线）" if baseline else "基线", "差值"]
    return _table(headers, rows)


def _context_size_table(payload: dict[str, Any]) -> str:
    """检索链路三阶段对照：召回池 → Rerank → 分数过滤（实际进入 LLM）。"""
    pool = payload.get("retrieval_pool") or {}
    reranked = payload.get("retrieval") or {}
    production = payload.get("retrieval_production") or {}
    sizes = payload.get("context_sizes") or {}

    rows: list[list[str]] = []
    if pool:
        rows.append(
            [
                "① 召回池（top_k=20，无过滤）",
                _num(pool["recall"].get("recall@5")),
                _num(pool["recall"].get("recall@10")),
                _num(pool["mrr_at_10"]),
                _num(pool["context_precision_at_5"]),
            ]
        )
    if reranked:
        rows.append(
            [
                "② Rerank 后（top_k=5，无分数过滤）",
                _num(reranked["recall"].get("recall@5")),
                _num(reranked["recall"].get("recall@10")),
                _num(reranked["mrr_at_10"]),
                _num(reranked["context_precision_at_5"]),
            ]
        )
    if production:
        rows.append(
            [
                "③ 分数过滤后（生产配置，进入 LLM）",
                _num(production["recall"].get("recall@5")),
                _num(production["recall"].get("recall@10")),
                _num(production["mrr_at_10"]),
                _num(production["context_precision_at_5"]),
            ]
        )
    table = _table(
        ["链路阶段", "Recall@5", "Recall@10", "MRR@10", "上下文精确率代理@5"], rows
    )
    if sizes:
        table += (
            f"\n\n平均上下文条数：召回池 {sizes.get('pool_mean', 0):.1f} → "
            f"Rerank 后 {sizes.get('unfiltered_mean', 0):.1f} → "
            f"分数过滤后 {sizes.get('production_mean', 0):.1f}；"
            f"有 {sizes.get('items_filtered_below_top5', 0)} 道题的最终上下文不足 5 条"
            "（说明分数过滤比 top_k 更早触发，context 被提前截断）。"
        )
    return table


def _category_table(payload: dict[str, Any]) -> str:
    by_category = payload["retrieval"].get("by_category", {})
    rows = [
        [
            category,
            f"{int(data['items'])}",
            _num(data["recall@5"]),
            _num(data["mrr@10"]),
            _num(data["ndcg@5"]),
        ]
        for category, data in sorted(by_category.items())
    ]
    return _table(["分类", "题量", "Recall@5", "MRR@10", "nDCG@5"], rows)


def _abstention_table(payload: dict[str, Any]) -> str:
    stats = payload["abstention"]
    rows = [
        ["可答题目数", f"{stats['answerable_items']}"],
        ["可答题目被回答", f"{stats['answerable_answered']}（回答率 {_pct(stats['answer_rate'])}）"],
        ["可答题目被误拒答", f"{stats['answerable_abstained']}（误拒答率 {_pct(stats['false_abstention_rate'])}）"],
        ["不可答题目数", f"{stats['no_answer_items']}"],
        ["不可答题目被拒答", f"{stats['no_answer_abstained']}（正确拒答率 {_pct(stats['abstention_recall'])}）"],
        ["不可答题目漏拒答", f"{stats['no_answer_answered']}（漏拒答率 {_pct(stats['over_answer_rate'])}）"],
        ["均衡准确率", _num(stats["balanced_accuracy"])],
    ]
    return _table(["项", "值"], rows)


def _score_separation_table(payload: dict[str, Any]) -> str:
    """可答题 vs 不可答题的召回分分布——解释阈值为什么定在这里。"""
    groups = {"可答题目": [], "不可答题目": []}
    for record in payload.get("items", []):
        key = "可答题目" if record.get("answerable") else "不可答题目"
        groups[key].append(float(record.get("best_score") or 0.0))
    rows = []
    for name, values in groups.items():
        if not values:
            rows.append([name, "-", "-", "-", "-"])
            continue
        ordered = sorted(values)
        median = ordered[len(ordered) // 2]
        rows.append(
            [
                name,
                f"{len(values)}",
                _num(ordered[0]),
                _num(median),
                _num(ordered[-1]),
            ]
        )
    return _table(
        ["分组", "题数", "最低分", "中位数", "最高分"], rows
    )


def _sweep_table(payload: dict[str, Any]) -> str:
    rows = [
        [
            _num(row["threshold"]),
            f"{row['answered']}",
            f"{row['abstained']}",
            _pct(row["abstention_recall"]),
            _pct(row["false_abstention_rate"]),
            _num(row["balanced_accuracy"]),
        ]
        for row in payload.get("threshold_sweep", [])
    ]
    return _table(
        ["召回分阈值", "回答题数", "拒答题数", "正确拒答率", "误拒答率", "均衡准确率"], rows
    )


def _generation_table(payload: dict[str, Any]) -> str:
    stats = payload["generation"]
    if not stats["evaluated"]:
        return "_本次运行使用 `--no-llm`，未评测生成质量。_"
    attempts = stats.get("judge_attempts", 0)
    retried = stats.get("judge_retried", 0)
    rows = [
        ["参与判定的回答数", f"{stats['evaluated']}"],
        ["其中系统故障（LLM 报错，已剔除）", f"{stats.get('generation_errors', 0)}（{_pct(stats.get('generation_error_rate', 0.0))}）"],
        ["裁判有效样本", f"{stats['judged']}"],
        ["裁判失败（解析/调用）", f"{stats['judge_errors']}"],
        ["正确性（含参考答案要点）", f"{stats['correct']}（{_pct(stats['correctness'])}）"],
        ["忠实度（被上下文支撑）", f"{stats['faithful']}（{_pct(stats['faithfulness'])}）"],
        ["空回答", f"{stats['empty_answers']}（{_pct(stats['empty_answer_rate'])}）"],
        ["答案含 [来源N] 标记", f"{stats['cited_answers']}（{_pct(stats['citation_rate'])}）"],
        ["裁判调用次数（含重试）", f"{attempts}"],
        ["其中经过重试的题数", f"{retried}"],
    ]
    table = _table(["项", "值"], rows)
    notes: list[str] = []
    if stats.get("generation_errors"):
        notes.append(
            f"有 {stats['generation_errors']} 题**系统故障**（LLM 限流/超时）"
            "——不是模型回答，已从正确性/忠实度的分母中剔除，"
            "可用 `python -m evaluation.runner --regenerate <report.json>` 重跑这些题。"
        )
    if stats["judge_errors"]:
        notes.append(
            f"有 {stats['judge_errors']} 题裁判无效，**已从正确性/忠实度的分母中剔除**"
            "（不用 0 分伪装成模型答错）。常见原因是 LLM 提供方的限流（429）或超时；"
            "裁判层已按 `EVAL_JUDGE_RETRY` / `EVAL_JUDGE_RETRY_DELAY` 做指数退避重试，"
            "可用 `python -m evaluation.runner --rejudge <report.json>` 在不重跑问答的前提下补判。"
        )
    for note in notes:
        table += f"\n\n> ⚠️ {note}"
    return table


def _threshold_recommendation(payload: dict[str, Any]) -> str:
    """把\"推荐阈值\"写成由数据推出的结论，而不是手填的数字。"""
    best = _best_threshold(payload)
    if best is None:
        return "_没有可用的阈值扫描结果。_"
    config = payload["run"]["pipeline_config"]
    current = config["ABSTENTION_SCORE_THRESHOLD"]
    mode = config["RETRIEVAL_MODE"]
    lines = [
        f"**推荐 `ABSTENTION_SCORE_THRESHOLD = {best['threshold']}`**"
        f"（`RETRIEVAL_MODE={mode}` 下的最优均衡点）：均衡准确率 "
        f"{_num(best['balanced_accuracy'])}，正确拒答率 {_pct(best['abstention_recall'])}，"
        f"误拒答率 {_pct(best['false_abstention_rate'])}。",
        "",
        f"本次运行实际取值 `ABSTENTION_SCORE_THRESHOLD={current}`，"
        "因此上表第 3 节的\"不可答题目被拒答\"才是当前配置的真实表现；"
        "调阈值前请先看召回分分布：两类题目的分数若大量重叠，"
        "提高阈值必然用\"误拒答可答题目\"换\"正确拒答\"。",
        "",
        "注意：**分数尺度与检索模式绑定**（vector 是余弦相似度，hybrid 是归一化融合分），"
        "换模式必须重新标定，不能直接沿用同一个数字。",
    ]
    return "\n".join(lines)


def _citation_table(payload: dict[str, Any]) -> str:
    stats = payload["citations"]
    rows = [
        ["已回答题目数", f"{stats['answered_items']}"],
        ["其中带结构化引用", f"{stats['items_with_citations']}（覆盖率 {_pct(stats['citation_rate'])}）"],
        ["引用与上下文一致", f"{stats['consistent_items']}（一致性 {_pct(stats['consistency_rate'])}）"],
        [
            "答案中出现自造引用编号",
            f"{stats['items_with_fabricated_reference']}（{_pct(stats['fabricated_reference_rate'])}）",
        ],
        ["引用总数", f"{stats['total_citations']}"],
        ["含 page/section 定位", f"{stats['located_citations']}（定位覆盖 {_pct(stats['locator_coverage'])}）"],
        [
            "答案中出现 `[来源N]` 标记",
            f"{stats['reference_marker_items']} 题（{_pct(stats['reference_marker_items'] / stats['answered_items']) if stats['answered_items'] else '—'}）",
        ],
    ]
    table = _table(["项", "值"], rows)
    if stats["answered_items"] and not stats["reference_marker_items"]:
        table += (
            "\n\n> 说明：结构化引用（API 返回）与上下文一致性均正常，但答案正文里**一个 "
            "`[来源N]` 标记都没有**。查看默认 RAG Prompt 可知它只要求「仅根据参考知识回答」，"
            "并未要求模型标注来源编号；上下文里已经有 `[来源N]` 编号，"
            "只需在 Prompt 中补一句「引用时标注 [来源N]」即可让「引用」在答案里真正闭环。"
            "本次评测保持 Prompt 不变，以便如实地衡量当前状态。"
        )
    return table


def _failure_cases(payload: dict[str, Any], limit: int = 12) -> str:
    """List concrete failures so the report cannot hide behind averages."""
    misses: list[str] = []
    unfaithful: list[str] = []
    empty: list[str] = []
    wrong_abstain: list[str] = []

    for record in payload["items"]:
        item_id = record["id"]
        question = record["question"]
        if record["answerable"] and record.get("retrieval", {}).get("first_relevant_rank") is None:
            misses.append(
                f"- `{item_id}` 未命中证据（返回 {record['retrieved']} 个 chunk，"
                f"最高分 {_num(record['best_score'])}）：{question}"
            )
        judgement = record.get("judgement") or {}
        if judgement and judgement.get("judge_error"):
            continue
        if judgement and not judgement.get("faithful"):
            unfaithful.append(
                f"- `{item_id}` 不忠实：{question}（裁判理由：{judgement.get('reason') or '无'}）"
            )
        if record.get("empty_answer"):
            empty.append(f"- `{item_id}` 空回答：{question}")
        if record["answerable"] and record.get("abstained"):
            wrong_abstain.append(
                f"- `{item_id}` 误拒答（{record.get('abstention_reason') or '—'}）：{question}"
            )
        if not record["answerable"] and not record.get("abstained"):
            wrong_abstain.append(
                f"- `{item_id}` 漏拒答（回答了无依据问题，最高分 {_num(record['best_score'])}）：{question}"
            )

    sections = []
    for title, entries in (
        ("检索未命中证据", misses),
        ("判为不忠实（可能有编造）", unfaithful),
        ("空回答", empty),
        ("拒答判定问题", wrong_abstain),
    ):
        if entries:
            shown = entries[:limit]
            more = f"\n（另有 {len(entries) - limit} 条同类问题，详见 JSON 结果）" if len(entries) > limit else ""
            sections.append(f"**{title}（{len(entries)} 条）**\n\n" + "\n".join(shown) + more)
    return "\n\n".join(sections) if sections else "_本次运行没有发现上述类型的失败案例。_"


def _best_threshold(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    sweep = payload.get("threshold_sweep") or []
    if not sweep:
        return None
    return max(sweep, key=lambda row: (row["balanced_accuracy"], -row["false_abstention_rate"]))


def _run_config_table(payload: dict[str, Any]) -> str:
    run = payload["run"]
    config = run["pipeline_config"]
    rows = [
        ["检索模式", f"`RETRIEVAL_MODE={config['RETRIEVAL_MODE']}`"],
        ["融合权重", f"vector={config['HYBRID_VECTOR_WEIGHT']} / bm25={config['HYBRID_BM25_WEIGHT']}，召回 K={config['HYBRID_RECALL_K']}"],
        ["重排", f"`{config['RERANKER_TYPE']}`（enabled={config['RERANKER_ENABLED']}，top_k={config['RERANKER_TOP_K']}）"],
        ["上下文阈值", f"`CONTEXT_SCORE_THRESHOLD={config['CONTEXT_SCORE_THRESHOLD']}`（{config['CONTEXT_SCORE_SOURCE']}）"],
        [
            "拒答阈值",
            f"min_chunks={config['ABSTENTION_MIN_CONTEXT_CHUNKS']}，"
            f"score={config['ABSTENTION_SCORE_THRESHOLD']}，rerank={config['ABSTENTION_RERANK_THRESHOLD']}",
        ],
        ["Query Rewrite", f"`QUERY_REWRITE_ENABLED={config['QUERY_REWRITE_ENABLED']}`"],
        ["切分参数", f"chunk_size={config['CHUNK_SIZE']}，overlap={config['CHUNK_OVERLAP']}"],
        ["嵌入模型", f"`{config['EMBEDDING_MODEL']}`（{config['EMBEDDING_DIM']} 维）"],
        ["生成模型", f"`{config['LLM_PROVIDER']}` / `{config['LLM_MODEL']}`"],
        ["裁判模型", f"`{run['judge_model']}`" if run.get("judge_model") else "未启用"],
    ]
    return _table(["配置项", "本次取值"], rows)


def _corpus_table(payload: dict[str, Any]) -> str:
    rows = []
    for entry in payload["run"]["ingestion"]:
        rows.append(
            [
                f"`{entry['filename']}`",
                entry["role"],
                f"{entry['chars']}",
                f"{entry['chunks']}",
                entry["status"],
            ]
        )
    return _table(["文档", "角色", "字符数", "chunks", "入库状态"], rows)


METHODOLOGY = """### 方法与口径

1. **相关性判定用「证据关键词」而不是文档名**：同一事实可能同时出现在多篇文档中，
   按文档名判定会把正确答案判成错误。每题在 `rag_eval_v1.json` 里登记一组
   `evidence_keywords`，任一关键词出现在 chunk 原文中即视为该 chunk 相关。
2. **标注可执行校验**：所有 `evidence_keywords` 必须真的出现在语料里，
   所有 `no_answer` 题的 `probe_terms` 必须真的不出现；任一不满足评测直接中止
   （`tests/test_evaluation.py` 与 `--validate-only` 都会检查）。
3. **nDCG@5 采用二值相关性 + 单证据假设**（IDCG 取 rank=1），不是多级相关性 nDCG。
4. **上下文精确率是代理指标**：用「命中证据的 chunk 数 / 实际返回的 chunk 数」近似，
   因为无法为每个 chunk 做全量相关性标注。
5. **忠实度只看本次检索到的上下文**，与「是否包含参考答案要点」是两个独立判定。
6. **阈值扫描复用同一次运行的 trace**，不需要重新调用模型，因此可离线复算。

### 本次评测的边界（不要过度解读）

- 语言与领域单一：语料只有中文、7 篇文档（含 5 篇仓库自有文档作为干扰项），
  chunk 总量见上表；该规模足以暴露召回与拒答问题，但不能替代生产量级评测。
- 生成指标依赖单一裁判模型，**未做人工双标注**，因此正确性/忠实度应视为
  「下限证据」而不是绝对真值；裁判 JSON 解析失败的样本已从分母剔除并单独计数。
- 单次运行、单机、无并发：延迟数字只代表本机串行评测，不能作为容量结论。
- 评测与开发库完全隔离（临时 SQLite + 临时 Chroma + 临时 BM25 索引），
  结果可重复运行，但 ChromaDB/模型版本变化可能带来微小差异。
"""


def render_report(
    payload: dict[str, Any],
    baseline: Optional[dict[str, Any]] = None,
    title: str = "Knowledge Chat RAG 评测报告",
) -> str:
    """Render the full Markdown report from one (or two) run payloads."""
    run = payload["run"]
    retrieval = payload["retrieval"]
    abstention = payload["abstention"]
    generation = payload["generation"]
    citations = payload["citations"]
    best_threshold = _best_threshold(payload)

    recall5 = retrieval["recall"].get("recall@5", 0.0)
    recall10 = retrieval["recall"].get("recall@10", 0.0)
    baseline_recall5 = (
        baseline["retrieval"]["recall"].get("recall@5") if baseline else None
    )

    headline = [
        f"- **检索**：Recall@5 = {_num(recall5)}，Recall@10 = {_num(recall10)}，"
        f"MRR@10 = {_num(retrieval['mrr_at_10'])}，nDCG@5 = {_num(retrieval['ndcg_at_5'])}"
    ]
    if baseline_recall5 is not None:
        headline.append(
            f"- **与 vector 基线对比**：Recall@5 {_num(baseline_recall5)} → {_num(recall5)}"
            f"（{_delta(recall5, baseline_recall5)}）"
        )
    headline.append(
        f"- **拒答**：正确拒答率 {_pct(abstention['abstention_recall'])}，"
        f"漏拒答率 {_pct(abstention['over_answer_rate'])}，"
        f"误拒答率 {_pct(abstention['false_abstention_rate'])}，"
        f"均衡准确率 {_num(abstention['balanced_accuracy'])}"
    )
    if best_threshold:
        headline.append(
            f"- **阈值推荐**：召回分阈值 {_num(best_threshold['threshold'])} 时均衡准确率最高"
            f"（{_num(best_threshold['balanced_accuracy'])}，"
            f"正确拒答率 {_pct(best_threshold['abstention_recall'])}，"
            f"误拒答率 {_pct(best_threshold['false_abstention_rate'])}）"
        )
    if generation["evaluated"]:
        headline.append(
            f"- **生成**：有效裁判 {generation['judged']} 条，正确性 {_pct(generation['correctness'])}，"
            f"忠实度 {_pct(generation['faithfulness'])}，空回答 {generation['empty_answers']} 条"
            f"（{_pct(generation['empty_answer_rate'])}），裁判失败 {generation['judge_errors']} 条"
        )
    headline.append(
        f"- **引用**：结构化引用覆盖 {_pct(citations['citation_rate'])}，"
        f"与上下文一致性 {_pct(citations['consistency_rate'])}，"
        f"page/section 定位覆盖 {_pct(citations['locator_coverage'])}，"
        f"自造引用编号 {citations['items_with_fabricated_reference']} 题"
    )

    parts = [
        f"# {title}",
        "",
        f"> 自动生成于 {datetime.now(timezone.utc).isoformat()}（`python -m evaluation.report`）。",
        "> 所有数字直接来自评测 JSON 结果，未经手工调整。",
        "",
        "## 1. 结论速览",
        "",
        "\n".join(headline),
        "",
        "## 2. 运行配置",
        "",
        _run_config_table(payload),
        "",
        f"数据集 `{run['dataset']['path']}`（v{run['dataset']['version']}）："
        f"{run['dataset']['items']} 题，其中可答 {run['dataset']['answerable']}、"
        f"不可答 {run['dataset']['no_answer']}；分类 {run['dataset']['categories']}。",
        f"运行时间 {run['started_at']} → {run['finished_at']}，耗时 {run['duration_seconds']}s。",
        "",
        "## 3. 评测语料",
        "",
        _corpus_table(payload),
        "",
        f"合计 {run['corpus']['chars']} 字符，"
        f"{sum(entry['chunks'] for entry in run['ingestion'])} 个 chunk 进入检索库。",
        "",
        "## 4. 检索质量（可答题目）",
        "",
        _retrieval_table(payload, baseline),
        "",
        "排序质量与「实际进入 LLM 的上下文」对照（同一份 trace，两种口径）：",
        "",
        _context_size_table(payload),
        "",
        "按分类拆分（候选池口径）：",
        "",
        _category_table(payload),
        "",
        "## 5. 拒答与阈值标定",
        "",
        _abstention_table(payload),
        "",
        "召回分分布（判定阈值是否可分离两类题目）：",
        "",
        _score_separation_table(payload),
        "",
        "阈值扫描（复用同一次运行的召回分数，模拟不同 `ABSTENTION_SCORE_THRESHOLD`）：",
        "",
        _sweep_table(payload),
        "",
        _threshold_recommendation(payload),
        "",
        "## 6. 生成质量（真实 LLM 裁判）",
        "",
        _generation_table(payload),
        "",
        "## 7. 引用质量",
        "",
        _citation_table(payload),
        "",
        "## 8. 失败案例",
        "",
        _failure_cases(payload),
        "",
        "## 9. 方法论与局限",
        "",
        METHODOLOGY,
        "## 10. 如何复现",
        "",
        "```bash",
        "cd backend",
        "",
        "# 1. 校验评测集（不加载模型、不联网）",
        "python -m evaluation.runner --validate-only",
        "",
        "# 2. 检索指标（零成本、可离线回归）",
        "python -m evaluation.runner --no-llm --mode hybrid --out evaluation/reports/hybrid_retrieval.json",
        "python -m evaluation.runner --no-llm --mode vector --out evaluation/reports/vector_retrieval.json",
        "",
        "# 3. 完整评测（真实 LLM 生成 + 裁判）",
        "python -m evaluation.runner --mode hybrid --out evaluation/reports/hybrid.json",
        "python -m evaluation.runner --mode vector --out evaluation/reports/vector.json",
        "",
        "# 4. 生成报告",
        "python -m evaluation.report --current evaluation/reports/hybrid.json \\",
        "    --baseline evaluation/reports/vector.json --out ../docs/RAG_EVALUATION.md",
        "```",
        "",
    ]
    return "\n".join(parts)


def load_payload(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.report",
        description="把评测 JSON 渲染成 Markdown 报告",
    )
    parser.add_argument("--current", required=True, help="当前（通常 hybrid）结果 JSON")
    parser.add_argument("--baseline", default=None, help="基线（通常 vector）结果 JSON")
    parser.add_argument("--out", default=None, help="输出 Markdown 路径（默认打印到 stdout）")
    parser.add_argument("--title", default="Knowledge Chat RAG 评测报告", help="报告标题")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    markdown = render_report(
        payload=load_payload(args.current),
        baseline=load_payload(args.baseline) if args.baseline else None,
        title=args.title,
    )
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
        print(f"报告已写入: {target}")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())


