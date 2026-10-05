# RAG 评测（Phase 2）

把 RAG 链路的"效果"从主观感受变成**可复现的数字**，并让这些数字无法被伪造。

```text
corpus（语料） ──真实入库──> 临时知识库 ──逐题提问──> 生产链路
                                                      │
                              ┌───────────────────────┤
                              ▼                       ▼
                     检索指标（离线可复现）      生成指标（真实 LLM 裁判）
                     Recall@K / MRR / nDCG       正确性 / 忠实度 / 引用
```

## 目录结构

| 路径 | 作用 |
|---|---|
| `corpus/` | 评测语料（含清单 `manifest.json`，记录来源与 sha256；`optional: true` 的条目在文件缺席时跳过，用于仓库不跟踪的干扰项） |
| `datasets/rag_eval_v1.json` | 评测集：71 题（59 可答 + 12 不可答） |
| `dataset.py` | 语料/数据集加载与**真实性校验** |
| `metrics.py` | 检索/拒答/生成指标的纯函数（无 I/O，可单测） |
| `judge.py` | LLM 裁判（严格 JSON、容错解析、失败隔离） |
| `runner.py` | CLI：建临时工作区 → 入库 → 逐题跑 → 写 JSON |
| `report.py` | JSON → Markdown 报告（`docs/RAG_EVALUATION.md` 由它生成） |
| `reports/` | 运行结果 JSON（**只提交正式报告**，规则见下） |

## 产物归档规则

评测运行会产出两类 JSON，归档口径不同：

| 类型 | 例子 | 是否入库 | 原因 |
|---|---|---|---|
| **正式报告** | `hybrid.json`（含 LLM 生成 + 裁判）、`hybrid_retrieval.json`、`vector_retrieval.json`（基线） | **提交** | 是 `docs/RAG_EVALUATION.md` 与后续对比引用的数据源，需要可追溯 |
| **冒烟 / 中间产物** | `_smoke_llm.json`、`smoke_no_llm.json`、`hybrid_before_rejudge.json` | **不提交**（`.gitignore` 已覆盖：`_*.json`、`smoke_*.json`、`*_before_*.json`） | 一次性的质量门禁与调参中间态，重跑即失效；入库只会让 `git log` 充满无意义的数字变更 |

判断标准只有一条：**这份 JSON 是否被文档或对比结论引用**。被引用 → 提交并连同
生成它的命令一起说明；没被引用 → 视为脚手架，留在本地。

> 重新生成正式报告时（会产生 API 费用）务必同时更新报告头部的运行配置，
> 否则「报告数字」与「报告声称的配置」会脱节 —— 这正是 `report.py` 从 JSON
> 直接渲染、不手工改数的原因。

## 快速开始

```bash
cd backend

# 0) 只校验评测集与语料（不加载模型、不联网、秒级）
python -m evaluation.runner --validate-only

# 1) 只跑检索链路：零成本、可离线回归
python -m evaluation.runner --no-llm --mode hybrid --out evaluation/reports/hybrid_retrieval.json
python -m evaluation.runner --no-llm --mode vector --out evaluation/reports/vector_retrieval.json

# 2) 完整评测（真实 LLM 生成答案 + LLM 裁判打分，会产生 API 费用与耗时）
python -m evaluation.runner --mode hybrid --out evaluation/reports/hybrid.json

# 3) 生成 Markdown 报告
python -m evaluation.report --current evaluation/reports/hybrid.json \
    --baseline evaluation/reports/vector_retrieval.json \
    --out ../docs/RAG_EVALUATION.md

# 4) 裁判被限流（429）丢分时：只补裁判，不重跑检索/生成
python -m evaluation.runner --rejudge evaluation/reports/hybrid.json
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--mode vector` | 纯向量检索（**基线对照**，`RETRIEVAL_MODE=vector`） |
| `--no-llm` | 跳过生成指标（不调用任何 LLM） |
| `--limit N` | 只跑前 N 题（冒烟） |
| `--query-rewrite` | 打开 Query Rewrite 做消融（默认关闭并记录在报告中） |
| `--judge-max-tokens` | 裁判单次 token 上限（默认 800；推理型模型需留足） |
| `--judge-retry` / `--judge-retry-delay` | 裁判瞬时错误（429/5xx/超时）重试次数与指数退避基数（默认 4 次 / 3s） |
| `--rejudge REPORT_JSON` | 对已有报告补裁判（默认原地写回，不重跑检索与生成） |
| `--allow-download` | 允许访问 HuggingFace（默认强制离线，只用本地缓存） |
| `--keep-workspace` | 保留临时工作区（排查入库问题时用） |
| `--tag` | 结果文件名标签，便于区分多次运行 |

## 限流/失败恢复（工程细节）

真实调用大模型时，"评测框架自己"也会失败。这里做了三层处理，保证失败
**可见、可恢复、不会被伪装成模型答错**：

1. **裁判层重试**：只对瞬时错误（`429` / `5xx` / 超时 / 连接失败）做指数退避
   （3s → 6s → 12s，上限 30s）；参数错误、鉴权失败不重试，避免无意义等待。
   实测一次性跑 71 题时有 20 题（28%）被免费额度的 429 打掉——重试是必需项。
2. **失败隔离**：重试耗尽后记 `judge_error`（含尝试次数），**从正确性/忠实度的
   分母中剔除**，在报告里单独列出。绝不用 0 分伪装成"模型答错"。
3. **`--rejudge` 补判**：只重跑裁判，不重跑检索与生成（省时省钱）。
   裁判需要的上下文优先取记录里落盘的 `context_text`；老报告没有该字段时，
   会重建隔离工作区、按生产链路**重算上下文**，并用 `(filename, chunk_index)`
   指纹校验与原报告是同一批 chunk（不一致会在 `rejudge_history` 里点名）。
   补判结果、尝试次数与来源写回报告，`generation` 指标随之重算。

## 评测指标

**检索（对 59 道可答题目）**

- `Recall@1/3/5/10`：前 K 个上下文 chunk 中是否出现支持答案的证据
- `MRR@10`：第一个证据 chunk 的排名倒数的均值
- `nDCG@5`：二值相关性 + 单证据假设（IDCG 取 rank=1）
- `上下文精确率代理@5`：命中证据的 chunk 数 / 返回的 chunk 数（噪声率的反向指标）
- `文档级命中@5`：gold 文档是否出现在前 5（仅诊断用，**不参与判定**）

**拒答（对 59 可答 + 12 不可答）**

- `正确拒答率`：不可答题目被拒答的比例
- `漏拒答率`：不可答题目仍被回答的比例（越大越危险）
- `误拒答率`：可答题目被拒答的比例
- `均衡准确率`：`(回答率 + 正确拒答率) / 2`
- 阈值扫描：复用同一次运行的召回分数，模拟不同 `ABSTENTION_SCORE_THRESHOLD`

**生成（真实 LLM，仅统计被回答的题目）**

- `正确性`：回答是否覆盖参考答案的关键事实且不矛盾
- `忠实度`：回答的每个事实性陈述是否被本次检索上下文支撑
- `空回答率`：模型返回空正文的比例（**独立计数，不混入正确率**）
- `引用`：结构化引用覆盖率、与上下文一致性、`page/section` 定位覆盖率

## 数据集格式

```json
{
  "id": "faq-12",
  "category": "faq",
  "answerable": true,
  "question": "无锡市工人文化宫的总建筑面积大约是多少？",
  "reference_answer": "总建筑面积大约 53000 平方米……",
  "evidence_keywords": ["53000平方米"],
  "gold_docs": ["wuxi_culture_palace_faq.txt"]
}
```

不可答题目改用 `probe_terms`：

```json
{
  "id": "na-02",
  "category": "no_answer",
  "answerable": false,
  "question": "Kubernetes HPA 的默认缩容稳定窗口是多少秒？",
  "probe_terms": ["缩容稳定窗口"]
}
```

新增题目时必须满足（`tests/test_evaluation.py` 会强制校验）：

1. `answerable=true` 的每个 `evidence_keywords` **必须真的出现在语料原文中**；
2. `answerable=false` 的每个 `probe_terms` **必须完全不出现**在任何语料中；
3. `id` 唯一，`category` 取值在 `dataset.VALID_CATEGORIES` 内。

这条规则的价值在第一次跑就被验证了：`na-11` 最初用 `Prometheus` 当探针词，
校验直接报出该词出现在仓库干扰文档里，题目随即换成语料真没有的 Kafka。

## 隔离与安全

- **不碰开发数据**：运行器在导入任何 `app.*` 模块之前，把 `DATABASE_URL`、
  `CHROMA_PERSIST_DIR`、`SPARSE_INDEX_PATH`、`UPLOAD_DIR` 全部指向系统临时目录，
  结束后删除（`--keep-workspace` 可保留）。
- **不碰生产配置**：默认强制 `HF_HUB_OFFLINE=1`，模型加载只用本地缓存，可复现。
- **失败不静默**：入库失败记录状态与错误信息；裁判失败记为 `judge_error` 并单独统计；
  数据集校验不通过直接中止，不产出"漂亮但不可信"的指标。

## 已知边界

见报告第 9 节。要点：语料规模小（7 篇 / 75 chunk）、裁判未经人工双标注、
单次运行无方差统计、延迟只代表本机串行评测。
