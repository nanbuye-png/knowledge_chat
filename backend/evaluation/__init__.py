"""RAG Evaluation package (Phase 2).

把 RAG 链路的"效果"从主观感受变成**可复现的数字**：

```text
评测语料(corpus) ──入库──> 临时知识库 ──逐题提问──> 真实链路
                                                    │
                            ┌───────────────────────┤
                            ▼                       ▼
                    检索指标(离线可复现)      生成指标(真实 LLM)
                    Recall@K / MRR / nDCG     正确性 / 忠实度 / 引用
```

模块
----
* :mod:`~evaluation.dataset` — 数据集加载与**真实性校验**（关键词必须真的出现在语料里）
* :mod:`~evaluation.metrics` — 纯函数检索/拒答指标（无 I/O、无网络、可单测）
* :mod:`~evaluation.judge` — LLM 裁判（正确性 / 忠实度 / 引用支撑）
* :mod:`~evaluation.runner` — CLI：建临时工作区 → 入库 → 跑题 → 产出 JSON
* :mod:`~evaluation.report` — JSON → Markdown 报告

用法::

    cd backend
    python -m evaluation.runner --mode hybrid      # 完整评测（含真实 LLM 生成指标）
    python -m evaluation.runner --mode vector      # Baseline 对照
    python -m evaluation.runner --no-llm           # 仅检索指标（离线、零成本）
"""
