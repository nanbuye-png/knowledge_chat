# AI Knowledge Chat — 基于 RAG 的智能知识库问答系统

> 面向企业知识管理场景设计，支持文档解析、向量检索、RAG 问答、引用溯源、
> 权限控制和多模型 Provider。
>
> v1.0.1 · FastAPI + React + ChromaDB

[架构文档](docs/architecture.md) ·
[RAG Pipeline](docs/rag_pipeline.md) ·
[RAG 评测报告](docs/RAG_EVALUATION.md) ·
[更新日志](CHANGELOG.md) ·
[接口文档](http://localhost:8000/docs)（本地启动后可见）

---

## ✨ 项目简介

### 为什么做这个项目

把一个文档丢给 LLM 很容易，难的是让答案**说得清出处**、**答不出来时承认答不出来**、
并且**能被别人管起来**（谁能看哪个库、用了多少 token、出错去哪查）。
这个项目就是从"能跑通 RAG"往"能交付给一个团队用"的方向做的：

- 检索链路不是一个 `similarity_search` 调用，而是
  Query 改写 → 混合检索（向量 + BM25）→ 阈值过滤 → 重排 → 上下文过滤 → 引用构建，
  每一步的中间结果都进 `metadata`，可以在前端 Pipeline 面板里看到；
- 答案带结构化引用（文件名 / 段落 / 页码 / 章节），并且有校验器检查"引用的编号是否真实存在"；
- 检索不到依据时走拒答（Abstention），**不调用 LLM**，杜绝编造；
- 权限、配额、审计、指标、限流都是后端一等公民，不是事后补的中间件。

### 解决什么问题

| 问题 | 这个项目的做法 |
|---|---|
| 文档格式杂（PDF / DOCX / MD / TXT / CSV / XLSX） | 每种格式一个 Parser，统一产出段落结构（含页码 / 标题） |
| 答案不可信、无从核对 | RAG 回答带 `citations` + `sources`，前端点开就能看原文片段 |
| 检索只靠向量，专有名词/编号召回差 | 默认 `RETRIEVAL_MODE=hybrid`：向量 + BM25 加权融合 |
| 相似度低也硬答 | 分数阈值过滤 + 可选拒答（阈值可按评测标定） |
| 多租户越权 | 知识库归属校验下沉到 API 与检索层（含会话一致性校验） |
| 模型不可换、成本不可见 | Provider 抽象 + 模型注册表 + token 用量统计与配额 |

### 目前处于什么阶段

**v1.0.1：功能闭环、可部署、可自查的稳定版本。**

- 后端 742 个测试全部通过（`cd backend && python -m pytest -q`，本机实测 2 分 49 秒）；
- 检索/生成质量有实测数据（71 题评测集，Recall@5 = 0.949，生成正确性 95.8%，
  详见 [docs/RAG_EVALUATION.md](docs/RAG_EVALUATION.md)）；
- Docker Compose（开发 / 生产）与 Kubernetes 原生清单可直接部署；
- 仍未落地的部分**在文档里逐条标注了 Planned**（Helm 资源模板、Grafana 面板等），
  不把规划写成已实现 —— 见文末 [⚠️ Known Limitations](#-known-limitations)。


---

## 🎯 核心功能

### 💬 AI Chat

- **知识库问答（RAG）**：选择知识库提问，回答携带引用卡片（文件名 / 段落 / 得分，可定位页码与章节）
- **普通 LLM 对话**：不走检索，直接调用 Provider
- **SSE 流式输出**：`POST /api/chat/stream`、`POST /api/knowledge/query/stream`，
  打字机式增量渲染，前端可展开 Pipeline 面板查看检索中间态
- **多轮会话**：会话列表、历史消息持久化、切换知识库
- **无依据时不硬答**：检索结果为空 → 拒答固定文案，不产生幻觉

### 📚 Knowledge Base

- **多格式解析**：PDF（PyMuPDF）、DOCX（python-docx）、DOC（olefile）、MD、TXT、CSV、XLSX（openpyxl）
- **Chunk 切分**：RecursiveChunker，按文档结构递归切分，`chunk_size` / `chunk_overlap` 支持**按知识库覆盖**
- **Embedding**：默认 `BAAI/bge-small-zh-v1.5`（512 维，本地推理），Provider 可切换
- **向量存储**：ChromaDB，按知识库隔离 collection，检索条件带知识库归属校验
- **异步入库**：上传请求立即返回，解析 / 切分 / 向量化交给本地 Worker 在**独立后台线程 + 独立事件循环**里执行
  （`WORKER_MAX_CONCURRENCY` 控并发，任务不绑在请求生命周期上），前端轮询文档状态（processing / completed / failed）
- **检索配置**：Top-K、切分参数、Embedding 模型按知识库配置（缺省回落全局 `settings`）

### 🏢 Platform

- **认证**：JWT（`Authorization: Bearer`）+ API Key（`X-API-Key`）双通道
- **RBAC**：ROOT / ADMIN / USER 三级，权限点校验（含遗留角色映射）
- **Organization**：组织 / 成员 / 部门结构
- **Knowledge ACL**：知识库粒度访问控制
- **会话与审计**：登录会话管理（可撤销）、关键操作写审计日志
- **限流**：按端点限流（Redis 或内存后端）
- **配额与用量**：token 用量记录，按用户 / 模型聚合的用量看板

### 🤖 AI Infrastructure

- **Provider 抽象**：LLM Provider 工厂（DeepSeek / Agnes），切换只改配置不改代码
- **Model Registry**：模型注册表（能力 / 上下文长度 / 供应商），含别名归一化迁移
- **Prompt 管理**：Prompt 模板 CRUD + 版本管理
- **运行时配置**：知识库级 AI 参数（切分 / Top-K / Embedding）与全局默认值的解析优先级
- **Tool Calling**：`kb_search`（复用生产检索链路 + 归属校验）、
  `calculator`（`ast.parse` + 白名单求值，**不使用 eval**）；
  端点 `GET /api/tools`、`POST /api/tools/run`（按序多次调用）、`POST /api/tools/{tool_name}/invoke`
- **Agents：Agent 最小真实路径（已实现，不是 Planned）** —— `agents` 表 +
  `/api/agents` CRUD + `POST /api/agents/{id}/execute`；确定性工具选择 →
  复用工具层的超时 / 次数上限 / 失败即停 → 汇总回答；未绑定模型时如实返回
  `answer_mode=tools_only`（工具结果汇总，不冒充模型生成）
- **Workflows：Workflow 最小真实路径（已实现，不是 Planned）** —— `workflows` 表 +
  `/api/workflows` CRUD + `POST /api/workflows/{id}/execute`；用户**显式声明**的有序
  步骤 + 条件分支 `when`（`always` / `previous_succeeded` / `previous_failed` /
  `input_is_math`）+ 状态传递（`{{input}}` / `{{steps.<步骤ID>.output.<字段>}}`）+
  逐步失败策略 `on_error`（abort / continue）；跳过的步骤带 `skip_reason`、
  失败的步骤带 `error.code`，都不静默

  > Agent 与 Workflow 的分工：Agent 是"动态规划 + 工具选择"，Workflow 是"显式编排"。
  > 两者共用同一份 `ToolRegistry`，**没有第二套工具执行**。

---

## 🧠 RAG Architecture

```text
                          ┌──────────────────── 入库（离线） ────────────────────┐
  PDF/DOCX/DOC/MD/TXT ──► Parser ──► RecursiveChunker ──► Embedding ──► ChromaDB
  CSV/XLSX                 │              │                 │              │
                       段落+页码/标题   chunk_size/overlap  bge-small-zh   按 KB 建 collection
                          └──────────────────── 任务表驱动，前端轮询状态 ────┘

                          ┌──────────────────── 问答（在线） ────────────────────┐
  用户提问 ──► Query Rewrite ──► Hybrid Retrieve ──► 阈值过滤 ──► Rerank ──► 上下文过滤
                 (可选，默认关)   向量 + BM25(K=20)   MIN_SCORE=0.3  top_k=5    CONTEXT_SCORE_THRESHOLD
                                        │
                                        └─► 无结果 ──► Abstention（固定文案，不调用 LLM）
                                        │
                                  CitationBuilder ──► Context 组装 ──► LLM ──► 答案 + 引用
```

### Document Ingestion

`DocumentService` → `KnowledgePipeline.process_document()` → `Parse → Chunk → Embed → VectorStore`。
切分参数、Embedding 模型从**知识库级配置**解析（`KnowledgeRuntimeConfigService`），
没有配置就回落全局 `settings`；入库由后台 Worker 异步执行（请求不等待解析完成），
失败会把原因写回文档状态，而不是让状态永远停在"处理中"。

### Retrieval

`RetrievalPipeline.retrieve()`（`backend/app/services/retrieval_pipeline.py`）是唯一检索入口，
Chat、`kb_search` 工具、评测脚本共用它，**不存在第二套检索实现**。链路每一步的中间结果
都写进 `RetrievalResult.metadata`（候选数、阈值后条数、重排结果、上下文过滤明细），
前端 Pipeline 面板与评测归因都读它。

### Generation

`ChatService.stream_query_knowledge()` 把 `context` + 最近 10 条 `history` 组装成 messages，
调用 Provider 流式生成；完成后按 `prompt_tokens` / `completion_tokens` / 延迟写入用量表。
引用编号由 `CitationBuilder` 统一分配（`[来源1]`、`[来源2]`…），Prompt 里明确要求"只用给定上下文回答"。

---

## 🔥 核心技术实现

### 文档解析

`services/parser/`：每种格式一个 Parser（`pdf_parser` / `docx_parser` / `doc_parser` /
`markdown_parser` / `text_parser` / `csv_parser` / `xlsx_parser`），统一继承 `BaseParser`
产出**带结构的段落**（正文 / 标题层级 / 页码），而不是一坨纯文本 ——
这是后面"引用能定位到页码与章节"的前提。扫描件 PDF（无文本层）当前会解析出空内容。

### Chunk 策略

`services/chunking/recursive_chunker.py`：优先按标题/段落/换行递归切分，
超长段落才按窗口切开，相邻 chunk 保留 `chunk_overlap` 重叠，避免答案被切断在边界上。
默认 `chunk_size=2000` / `chunk_overlap=200`，可按知识库覆盖（评测用的即是该默认值，
75 个 chunk / 115838 字符）。

### Embedding

`services/embedding/`：`EmbeddingProviderFactory` 管理 Provider
（`bge` / `jina` / `openai` / `voyage` / `default`），默认本地 `BAAI/bge-small-zh-v1.5`（512 维，
sentence-transformers 推理，不产生外部调用成本）。查询与文档共用同一 Provider 保证向量空间一致。

### Vector Search

**混合检索**（`RETRIEVAL_MODE=hybrid`，默认）：

1. 向量通道：ChromaDB 相似度检索，`HYBRID_RECALL_K=20`；
2. 稀疏通道：BM25（`SPARSE_BM25_K1=1.5` / `B=0.75`），索引来自库内 chunk 文本，句子切片后建索引；
3. 融合：两通道分数归一化后加权（`HYBRID_VECTOR_WEIGHT=0.5` + `HYBRID_BM25_WEIGHT=0.5`）；
4. 过滤：低于 `RETRIEVAL_MIN_SCORE=0.3` 的候选直接丢弃；
5. 重排：`RERANKER_ENABLED=true`，默认 `RERANKER_TYPE=lexical`（查询与 chunk 的词面重叠度，
   零依赖零下载），可切 `cross_encoder`（`BAAI/bge-reranker-base`，需下载模型）；
   重排超时 / 异常自动回退召回顺序，**永不因此让请求失败**；
6. 上下文过滤：`CONTEXT_SCORE_THRESHOLD`（默认 0.0 = 只做结构性过滤），
   被过滤掉的 chunk 与原因写进 metadata；
7. 缓存：`RETRIEVAL_CACHE_ENABLED=true`，`RETRIEVAL_CACHE_TTL=300`，
   key 含知识库 / 查询 / 配置指纹，只缓存"有结果"的成功路径。

**拒答（Abstention）**：`services/retrieval/abstention.py` 支持按
`no_context` / `insufficient_context` / 召回分 / 重排分四种依据拒答；默认阈值 0.0
（即只保留"无上下文"这种结构性拒答），需要严格拒答时按评测结论调阈值
（评测推荐 0.75，见 [评测报告 §5](docs/RAG_EVALUATION.md)）。

### Prompt Construction

`app/prompts/` 提供 Prompt Provider（默认实现 + 数据库版本），支持模板版本管理与运行时切换；
RAG Prompt 由 `ChatService._build_rag_prompt()` 组装：system 约束（只依据上下文、标注来源编号）
+ 上下文（`[来源N] 文件名：… (段落N) 内容：…`）+ 最近 10 条对话历史 + 当前问题。

### Citation

`services/citation/`：`builder` 从最终 chunk 生成结构化引用
（`document_id` / `filename` / `chunk_index` / `score`），`locator` 补页码与章节，
`validator` 校验模型输出里引用的编号**是否真实存在于本次上下文**（自造编号会被识别）。
评测结果：结构化引用覆盖 100%，与上下文一致率 84.5%，页码 / 章节定位覆盖 92.5%。

### Conversation Memory

消息持久化在 `messages` 表（用户消息在请求开始时落库，模型回答在流式结束后落库，
保证"只有真正拿到内容才写"）；多轮上下文由请求携带 `history`，服务端只取**最近 10 条**
（`history[-10:]`）注入 Prompt，避免上下文无限增长导致 token 成本失控与注意力稀释。

### SSE Streaming

`POST /api/chat/stream`、`POST /api/knowledge/query/stream` 返回 `text/event-stream`：

```text
data: {"token": "根据"}

data: {"token": "知识库"}

data: [DONE]
```

出错时先发一帧错误提示再发 `[DONE]`（不让前端一直转圈）；响应头带
`Cache-Control: no-cache` + `X-Accel-Buffering: no`（避免 Nginx 缓冲把流"攒"成一次性输出）。

### Provider Abstraction

`services/llm/`：`BaseLLMProvider` 定义 `chat()` / `stream_chat()`，
`LLMProviderFactory` 按 `LLM_PROVIDER` 选择实现（`deepseek` / `agnes`），
切换模型只改 `.env`（`LLM_PROVIDER` + `LLM_MODEL`），业务代码零改动；
模型注册表另有别名归一化，历史脏数据（如 `agens-*` 拼写）由迁移统一。

---

## 🏗️ System Architecture

### 后端分层

```text
                ┌────────────────────────── React SPA (Vite) ──────────────────────────┐
                │  chat / knowledge / ai / organization / admin / monitoring / account │
                └───────────────────────────────┬──────────────────────────────────────┘
                                                │ REST + SSE（JWT / API Key）
                ┌───────────────────────────────▼──────────────────────────────────────┐
                │ FastAPI  api/  （chat · knowledge_query · documents · knowledge_bases │
                │        · llm_model · prompt_* · tools · agents · workflows · admin/*）│
                ├──────────────────────────────────────────────────────────────────────┤
                │ 鉴权中间件：JWT / API Key · RBAC 权限点 · 限流 · 审计 · 请求日志     │
                ├──────────────────────────────────────────────────────────────────────┤
                │ services/                                                            │
                │   chat_service ──► retrieval_pipeline ──► retrieval/(hybrid·reranker)│
                │        │                    │                  │                      │
                │        │                    │            citation/(builder·validator)│
                │        ▼                    ▼                                         │
                │   llm/(provider 工厂)   query/(改写)   knowledge/(pipeline·config)    │
                │   usage · metrics · cache · tasks/(异步入库) · tools · agent · workflow│
                ├──────────────────────────────────────────────────────────────────────┤
                │ storage/  SQLAlchemy(async) + ChromaDB     models/ 22 个模型          │
                └──────────────────────────────────────────────────────────────────────┘
                        │                                  │
                 PostgreSQL / SQLite                 ChromaDB 持久化目录
```

一次问答的调用顺序：
`api/knowledge_query.py` → 校验知识库归属 → `chat_service.stream_query_knowledge()`
→ `retrieval_pipeline.retrieve()`（改写 → 混合检索 → 过滤 → 重排 → 上下文过滤 → 引用）
→ `LLMProvider.chat/stream` → `usage_service.record()` → SSE 分帧返回。

### 数据模型

22 个模型 / 25 个 Alembic 迁移，覆盖：用户与凭证（`users` / `user_sessions` / `api_keys`）、
知识与文档（`knowledge_bases` / `documents` / `chunks` / `knowledge_configs` / 知识 ACL）、
对话（`conversations` / `messages`）、组织（`organizations` / `members` / `departments`）、
AI 配置（`llm_models` / `prompt_templates` / `prompt_versions`）、
编排（`agents` / `workflows`）、用量与审计（`llm_usages` / `audit_logs` / `usage` / `quota`）。

---

## 🛠️ 技术栈

### 后端

| 组件 | 技术 |
|---|---|
| Web 框架 | FastAPI（Python 3.12）+ Uvicorn |
| ORM / 迁移 | SQLAlchemy 2.0（async）+ Alembic |
| 数据库 | SQLite（开发）/ PostgreSQL 16（生产，asyncpg） |
| 向量存储 | ChromaDB（本地持久化） |
| 嵌入模型 | sentence-transformers · `BAAI/bge-small-zh-v1.5`（512 维） |
| 检索 | 自研 Hybrid（向量 + BM25）· Reranker · ContextFilter · Abstention |
| 文档解析 | PyMuPDF · python-docx · olefile · openpyxl |
| LLM Provider | DeepSeek · Agnes（OpenAI 兼容协议） |
| 认证 | PyJWT + passlib(bcrypt) |
| 缓存 / 限流 | Redis（或内存后端） |
| 可观测 | loguru · prometheus-client · psutil |

### 前端

| 组件 | 技术 |
|---|---|
| 框架 / 语言 | React 18 + TypeScript |
| 构建 | Vite 5 |
| 样式 | Tailwind CSS |
| 状态管理 | Zustand（`store/auth.ts` / `store/model.ts`） |
| 路由 | React Router 6（含 403 / 404 页） |
| 渲染 | react-markdown + remark-gfm + rehype-raw（代码高亮 react-syntax-highlighter） |
| 动效 / 图标 | framer-motion · lucide-react |

### 部署与工程

| 组件 | 技术 | 状态 |
|---|---|---|
| 容器化 | Dockerfile.backend / Dockerfile.frontend + Compose（dev / prod） | ✅ 可直接使用 |
| 反向代理 | Nginx（HTTP / HTTPS，50MB 上传上限，`X-Forwarded-For` 加固） | ✅ |
| 编排 | Kubernetes 原生清单（`k8s/`，含 PVC / Ingress / 单副本约束） | ✅ |
| 编排 | Helm Chart（`helm/knowledge-chat/`） | ⚠️ **Planned**（仅 `values.yaml` 骨架，无资源模板） |
| CI | GitHub Actions：后端 pytest（PostgreSQL + Redis service）+ 前端 `npm run build` | ✅ |
| 监控 | 应用内监控面板 + `/metrics`（Prometheus 文本格式） | ✅ |
| 监控 | Grafana 面板 / 告警规则 | ⚠️ **Planned**（仅提供 `monitoring/prometheus/prometheus.yml`） |

---


## 📁 项目结构

```text
knowledge_chat/
├── backend/
│   ├── app/
│   │   ├── api/            # chat · knowledge_query · documents · knowledge_bases · llm_model
│   │   │                   # prompt_* · tools · agents · workflows · admin/* · health
│   │   ├── auth/           # JWT 认证
│   │   ├── core/           # 配置 · 日志 · 异常契约 · 权限 · 中间件
│   │   ├── models/         # 22 个 SQLAlchemy 模型
│   │   ├── prompts/        # Prompt Provider（default / database / factory / resolver）
│   │   ├── schemas/        # Pydantic 请求响应
│   │   ├── services/
│   │   │   ├── retrieval/  # 向量 · BM25 · 混合融合 · 重排 · 上下文过滤 · 拒答
│   │   │   ├── citation/   # 引用构建 · 定位 · 校验
│   │   │   ├── chunking/   # RecursiveChunker
│   │   │   ├── embedding/  # Provider 工厂 + bge/jina/openai/voyage
│   │   │   ├── llm/        # Provider 工厂 + deepseek / agnes
│   │   │   ├── query/      # Query 改写
│   │   │   ├── knowledge/  # 入库 Pipeline · 运行时配置 · 上下文
│   │   │   ├── tools/      # ToolRegistry + kb_search / calculator
│   │   │   ├── agent/      # 确定性工具选择 + 受限执行
│   │   │   ├── workflow/   # 显式编排（模板 · 分支 · 失败策略）
│   │   │   ├── cache/      # Redis / 内存缓存 + 检索缓存
│   │   │   ├── tasks/      # 异步入库任务
│   │   │   └── ...         # chat · usage · metrics · system_monitor · security
│   │   └── storage/        # DB 会话 + 向量存储
│   ├── alembic/versions/   # 25 个迁移
│   ├── evaluation/         # RAG 评测：数据集 · 指标 · 裁判 · 报告
│   ├── scripts/            # create_root.py 等
│   └── tests/              # 51 个测试文件 / 742 个用例
├── frontend/
│   └── src/
│       ├── api/            # 接口客户端（含 SSE 封装）
│       ├── components/     # 公共组件
│       ├── pages/          # chat · knowledge · ai · organization · admin · monitoring · account
│       ├── store/          # Zustand
│       ├── router/         # 路由与守卫
│       └── hooks/ · utils/ · layouts/
├── docs/                   # architecture · rag_pipeline · RAG_EVALUATION · provider_system …
├── monitoring/prometheus/  # 抓取配置（Grafana 面板待补）
├── nginx/                  # 反向代理配置（HTTP / HTTPS）
├── k8s/                    # Kubernetes 清单
├── helm/knowledge-chat/    # Helm Chart（Planned）
├── docker-compose.yml      # 开发环境
├── docker-compose.prod.yml # 生产环境
├── CHANGELOG.md · VERSION
└── README.md
```

---

## 🚀 Quick Start（本地开发）

### 环境要求

- Python 3.12+
- Node.js 18+ / npm 9+

### 后端

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # 填入 LLM API Key（DEEPSEEK_API_KEY 或 AGNES_API_KEY）
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 初始化 ROOT 用户

```bash
cd backend
# Windows PowerShell:
$env:ROOT_PASSWORD="your_secure_password"; python scripts/create_root.py
# Linux/macOS:
ROOT_PASSWORD=your_secure_password python scripts/create_root.py
```

### 访问

- 前端界面：<http://localhost:5173>
- 接口文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/health>

> 开发环境默认用 SQLite + 本地 ChromaDB，无需额外服务；第一次提问前先在
> 「知识库」页创建知识库并上传几份文档（解析 + 向量化需要一点时间，文档状态会显示进度）。

---


## 🐳 Docker Deployment

### 一、开发环境（Docker Compose）

运行 **PostgreSQL + Redis + Backend + Frontend + Nginx**，统一从 <http://localhost> 访问。

```bash
# 1. 准备环境变量
cp .env.example .env
#   使用 DeepSeek：LLM_PROVIDER=deepseek、LLM_MODEL=deepseek-chat、DEEPSEEK_API_KEY=sk-xxx
#   使用 Agnes：   LLM_PROVIDER=agnes、LLM_MODEL=agnes-2.5-flash、AGNES_API_KEY=sk-xxx

# 2. 构建并启动
docker compose up -d --build

# 3. 初始化 ROOT 用户
docker compose exec backend python scripts/create_root.py
# Windows PowerShell 传环境变量：
docker compose exec -e ROOT_PASSWORD=your_secure_password backend python scripts/create_root.py

# 4. 查看状态与日志
docker compose ps
docker compose logs -f backend
```

访问：前端 <http://localhost> 、接口文档 <http://localhost/api/> 或 <http://localhost:8000/docs> 、
健康检查 <http://localhost/api/health>。

### 二、生产环境（Docker Compose）

```bash
# 1. 基于模板创建生产环境变量
cp .env.production .env.production.local

# 2. 编辑 .env.production.local，至少替换：
#    POSTGRES_PASSWORD / SECRET_KEY（openssl rand -hex 32）/ 使用的 LLM API Key / CORS_ORIGINS
#    SECRET_KEY 为占位或过短时，生产启动会直接 fail-fast；生产默认关闭 /docs、/redoc、/openapi.json
#    （临时需要时设 ENABLE_API_DOCS=true）

# 3. 构建并启动
docker compose --env-file .env.production.local -f docker-compose.prod.yml up -d --build

# 4. 初始化 ROOT 用户（同开发环境命令，换成 -f docker-compose.prod.yml）
docker compose -f docker-compose.prod.yml exec backend python scripts/create_root.py
```

#### HTTPS（可选）

1. 证书放入 `./certs/`（`fullchain.pem` / `privkey.pem`）；
2. 编辑 `docker-compose.prod.yml`：取消 `nginx` 的 443 端口与 `./certs` 挂载注释，
   把挂载配置从 `nginx.conf` 换成 `nginx.ssl.conf`；
3. `docker compose --env-file .env.production.local -f docker-compose.prod.yml up -d`。

#### 常用运维命令

```bash
docker compose -f docker-compose.prod.yml ps                      # 服务状态
docker compose -f docker-compose.prod.yml logs -f backend         # 后端日志
git pull && docker compose --env-file .env.production.local -f docker-compose.prod.yml up -d --build   # 更新部署
docker compose -f docker-compose.prod.yml down                    # 停止（保留数据卷）
docker compose -f docker-compose.prod.yml down -v                 # ⚠️ 连数据卷一起删（数据会清空）

# 数据库备份 / 恢复
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U postgres knowledge_chat > backup.sql
docker compose -f docker-compose.prod.yml exec -T postgres psql -U postgres knowledge_chat < backup.sql
```

#### 生产拓扑

```text
                          ┌─────────────────────────────┐
         HTTP/HTTPS       │  Nginx (80/443)             │
      Browser ───────────►│  - /api/* → backend:8000    │
                          │  - /*     → frontend:80     │
                          └──────────┬──────────────────┘
                                     │
                 ┌───────────────────┼───────────────────┐
        ┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐
        │ backend:8000    │ │ frontend:80     │ │ redis:6379      │
        │ FastAPI + RAG   │ │ 静态资源        │ │ 缓存 / 限流      │
        └────────┬────────┘ └─────────────────┘ └─────────────────┘
                 │
        ┌────────▼────────┐
        │ postgres:5432   │   + 命名卷：uploads / chroma_db
        │ 业务数据         │
        └─────────────────┘
```

### 三、镜像构建与发布

```bash
docker build -f Dockerfile.backend  -t ghcr.io/nanbuye-png/knowledge_chat/backend:1.0.1  .
docker build -f Dockerfile.frontend -t ghcr.io/nanbuye-png/knowledge_chat/frontend:1.0.1 .
docker login ghcr.io
docker push ghcr.io/nanbuye-png/knowledge_chat/backend:1.0.1
docker push ghcr.io/nanbuye-png/knowledge_chat/frontend:1.0.1
```

### 四、Kubernetes（原生清单）

```bash
kubectl apply -f k8s/secret.yaml              # 先改成真实密钥（SECRET_KEY 必填）
kubectl apply -f k8s/configmap.yaml           # 调整 CORS_ORIGINS 等
kubectl apply -f k8s/pvc.yaml                 # uploads + chroma_db 持久卷（Deployment 依赖它）
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/hpa.yaml
```

> ⚠️ **后端在 Kubernetes 里是"单副本"设计**：向量库是 Pod 本地的 ChromaDB
> （数据落在 `/app/chroma_db`）。扩到多副本不会更稳，而是让每个 Pod 各持一份互相看不见的
> 向量数据、检索结果随机分叉。因此 `k8s/backend-deployment.yaml` 固定 `replicas: 1` +
> `strategy: Recreate`（RWO 卷不适合滚动更新），`k8s/hpa.yaml` 的上下限也都是 1。
> 需要横向扩容时，先把向量库外置（独立 Chroma 服务 / pgvector 等）。

> 上传体积上限在入口处由 `nginx.ingress.kubernetes.io/proxy-body-size: 50m` 控制，
> 与后端 `MAX_FILE_SIZE` 保持一致。
> Helm Chart 目前是 Planned，请使用上面的原生清单（`helm install` 不会创建任何资源）。

---


## 🧪 Testing

### 怎么跑

```bash
# 后端：51 个测试文件、742 个用例（本机实测 742 passed，2 分 49 秒）
cd backend && python -m pytest -q

# 只跑某个模块
cd backend && python -m pytest tests/test_workflows.py -v

# 前端：TypeScript 类型检查 + 生产构建
cd frontend && npm run build
```

测试基线的事实：`742 passed / 0 failed`（`backend/conftest.py` 用真实 SQLite，
schema 由模型元数据创建，不是 mock 出来的假库）。工具层 / Agent / Workflow 的测试
断言的是**真实路由与生产 `ToolRegistry` 复用**，而不是玩具替身。

### 测什么

| 层 | 覆盖内容 |
|---|---|
| 单元 | Parser · Chunker · Retriever/BM25/Reranker · Citation · 工具（含 `calculator` AST 白名单） |
| 服务 | `RetrievalPipeline`（改写 / 过滤 / 重排 / 缓存）· Agent/Workflow 执行器与错误契约 |
| API | 认证与 RBAC · 知识库 CRUD 与归属校验 · 会话/消息 · 工具 / Agent / Workflow 端点 · 参数校验（400 而非 500） |
| 回归 | 越权（IDOR）· naive/aware 时间 · 迁移建表 · 前端契约（禁止用假数据冒充功能） |

### RAG 质量评测（不是"感觉还行"）

`backend/evaluation/` 是可复跑的评测链路（数据集 → 检索/生成 → LLM 裁判 → 报告）：

```bash
cd backend && python -m evaluation.runner    # 跑评测
cd backend && python -m evaluation.report    # 生成 docs/RAG_EVALUATION.md
```

最近一次结果（71 题：可答 59 / 不可答 12；语料 115838 字符 / 75 chunk）：

| 指标 | Hybrid（默认） | Vector 基线 |
|---|---|---|
| Recall@5 | **0.949** | 0.915 |
| MRR@10 | **0.818** | 0.812 |
| nDCG@5 | **0.851** | 0.838 |
| 文档级命中@5 | 1.000 | 0.983 |

生成：有效裁判 71 条，正确性 **95.8%**，忠实度 **97.2%**，空回答 1 条；
引用：结构化引用覆盖 **100%**，与上下文一致率 84.5%，page/section 定位覆盖 92.5%，
自造引用编号 0 题。完整数据与分类拆分见 [docs/RAG_EVALUATION.md](docs/RAG_EVALUATION.md)。

### CI

`.github/workflows/ci.yml`：push / PR 触发，起 PostgreSQL 16 + Redis 7 service，
在 Python 3.12 下跑 `pytest tests/ -v --tb=short`，再用 Node 20 跑 `npm ci && npm run build`。
`docker-build.yml` 负责镜像构建。

---

## 🔐 Security

| 能力 | 实现 |
|---|---|
| 认证 | JWT（`Authorization: Bearer`，含过期与用户状态校验）+ API Key（`X-API-Key`，可创建 / 撤销） |
| 会话管理 | 登录会话表可查询、可撤销（账号页与管理端）；token 每次请求校验用户状态，已删除 / 已停用用户直接被拒 |
| RBAC | ROOT / ADMIN / USER 三级，权限点集中校验，管理后台按权限渲染 |
| 知识库 ACL | 知识库粒度访问控制；**归属校验在 API 与检索两条路径上都做**（含会话与知识库一致性校验，避免 IDOR） |
| API Key | 支持创建、吊销、按用户隔离 |
| 限流 | 提问按角色每日限额（`/api/chat/*`）+ 路由级单端点突发限额，统一走同一份 `check_rate_limit`（Redis 或内存后端） |
| 审计 | 关键操作写审计日志，管理端可检索 |
| 密钥安全 | 生产环境 `SECRET_KEY` 为占位 / 过短时**直接拒绝启动**（fail-fast）；生产默认关闭 `/docs`、`/redoc`、`/openapi.json` |
| 错误契约 | 统一 `{"code","message","request_id"}`，不把 `str(e)` / 堆栈返回给客户端，原始异常只进日志 |
| 工具安全 | `calculator` 用 `ast.parse` + 节点白名单求值（**不使用 `eval`**）；工具调用有超时与次数上限 |

> 已知待加固项（见文末 Roadmap）：前端 Markdown 渲染未加内容净化（`rehype-sanitize`）、
> 容器未以非 root 运行、CSP / HSTS 未启用。

---

## 📊 Observability

| 维度 | 实现 |
|---|---|
| Metrics | 后端 `/metrics`（Prometheus 文本格式）：HTTP 请求 / 延迟 / 错误、LLM tokens / 延迟 / 成本、RAG 各阶段耗时（rewrite → embed → retrieve → rerank → context_filter → llm）、chunk 数量、拒答原因、重试与文档状态流转、缓存命中率 |
| 应用内面板 | 管理后台「监控」：系统健康、在线监控、API 性能、AI 指标（模型排行）、Token 分析、错误追踪 |
| Token 用量 | 每次 LLM 调用记录 provider / model / prompt / completion / 延迟，可按时段与模型聚合（含成本视角） |
| 日志 | loguru 结构化日志 + 请求日志中间件；错误日志带 `request_id`，可与接口响应里的 `request_id` 对齐排查 |
| 错误追踪 | 统一异常处理 + 错误面板（按端点 / 类型聚合），500 只暴露固定文案与 `code` |
| 检索可观测 | 每次检索的 `metadata`（候选数、阈值后条数、重排结果、上下文过滤明细）随响应返回，前端可展开查看 |

> 外部 Prometheus + Grafana 整套栈：抓取配置模板已提供
> （`monitoring/prometheus/prometheus.yml`），**Grafana 面板与告警规则仍属 Planned**。

---


## 🔧 环境变量

### 开发 `.env`（Docker Compose / 本地后端）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `LLM_PROVIDER` | LLM 提供商（`deepseek` / `agnes`） | `deepseek` |
| `LLM_MODEL` | 模型名（须与 Provider 匹配，如 `deepseek-chat` / `agnes-2.5-flash`） | `deepseek-chat` |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | DeepSeek 密钥与地址 | - / `https://api.deepseek.com` |
| `AGNES_API_KEY` / `AGNES_API_BASE` | Agnes 密钥与地址 | - / `https://apihub.agnes-ai.com/v1` |
| `EMBEDDING_MODEL` | 嵌入模型 | `BAAI/bge-small-zh-v1.5` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 默认切分参数（可按知识库覆盖） | `2000` / `200` |
| `DATABASE_TYPE` / `DATABASE_URL` | 数据库类型与连接串 | `sqlite` / 本地文件 |
| `CHROMA_PERSIST_DIR` | 向量库持久化目录 | `./chroma_db` |
| `MAX_FILE_SIZE` / `UPLOAD_DIR` | 上传体积上限与目录 | 见 `.env.example` |
| `SECRET_KEY` | JWT 密钥（生产环境占位 / 过短会拒绝启动） | 仅开发可用 |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Compose 数据库账号 | `postgres` |

> 切换模型只需改 `LLM_PROVIDER` + `LLM_MODEL`，无需改代码；启动时会打印当前
> Provider 与模型，配置不匹配或缺少 Key 会输出 `⚠️ LLM 配置检查` 告警。

### 检索 / 编排相关（`backend/app/core/config.py`）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `RETRIEVAL_MODE` | 检索模式：`hybrid`（向量 + BM25）/ `vector`（评测基线） | `hybrid` |
| `RETRIEVAL_MIN_SCORE` | 召回分下限，低于它的候选直接丢弃 | `0.3` |
| `HYBRID_VECTOR_WEIGHT` / `HYBRID_BM25_WEIGHT` / `HYBRID_RECALL_K` | 融合权重与召回池大小 | `0.5` / `0.5` / `20` |
| `SPARSE_BM25_K1` / `SPARSE_BM25_B` | BM25 参数 | `1.5` / `0.75` |
| `RERANKER_ENABLED` / `RERANKER_TYPE` / `RERANKER_TOP_K` / `RERANKER_TIMEOUT` | 重排开关、类型（`lexical` / `cross_encoder`）、保留条数、超时 | `true` / `lexical` / `5` / `10.0` |
| `CONTEXT_SCORE_THRESHOLD` / `CONTEXT_SCORE_SOURCE` | 进入 LLM 的上下文分数阈值与取分来源 | `0.0` / `auto` |
| `RETRIEVAL_CACHE_ENABLED` / `RETRIEVAL_CACHE_TTL` | 检索缓存开关与 TTL（秒） | `true` / `300` |
| `ABSTENTION_*` | 拒答阈值（`0.0` = 只做结构性拒答） | `0.0` |
| `QUERY_REWRITE_ENABLED` | Query 改写开关（评测中为关闭状态） | `false` |
| `TOOL_TIMEOUT_SECONDS` / `TOOL_MAX_CALLS_PER_REQUEST` | 工具超时与单请求最大调用次数 | 见 `config.py` |
| `WORKFLOW_MAX_STEPS` | Workflow 步骤上限（前端经 `/api/workflows/limits` 读取并提示） | `5` |
| `CACHE_BACKEND` / `REDIS_HOST` / `REDIS_PORT` | 缓存后端（`memory` / `redis`） | `memory` |

### 生产 `.env.production.local`

| 变量 | 说明 | 是否必填 |
|---|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL 密码 | ✅ |
| `SECRET_KEY` | JWT 密钥（`openssl rand -hex 32`） | ✅（占位 / 过短会拒绝启动） |
| `DEEPSEEK_API_KEY` 或 `AGNES_API_KEY` | 与 `LLM_PROVIDER` 对应的密钥 | ✅ |
| `CORS_ORIGINS` | 允许的跨域来源 | 建议显式设置 |
| `ENABLE_API_DOCS` | 生产是否开放 `/docs`（默认关闭） | 否 |
| `ACCESS_TOKEN_EXPIRE_HOURS` | Token 过期小时数 | 否 |
| `LLM_PROVIDER` / `LLM_MODEL` | 模型选择 | 否 |

---

## ⚠️ Known Limitations

这些是**当前真实存在**的限制，不是待办清单里的客套话：

1. **Helm Chart 只有骨架**：`helm/knowledge-chat/` 目前只有 `values.yaml` + `_helpers.tpl`，
   `helm install` 不会创建任何资源 —— 生产请用 `k8s/` 原生清单。
2. **Grafana 面板 / 告警规则未落地**：只提供了 Prometheus 抓取配置模板；
   应用内监控面板与 `/metrics` 是可用的。
3. **向量库是本地的，因此后端只能单副本**：ChromaDB 数据在每个 Pod/容器本地目录，
   Kubernetes 里固定 `replicas: 1`。要横向扩容必须先把向量库外置。
4. **拒答默认只做"结构性"拒答**：`ABSTENTION_*` 阈值默认为 `0.0`，
   即"检索不到上下文"才拒答。实测 12 道不可答题目**全部漏拒答**（正确拒答率 0%）；
   评测推荐召回分阈值 0.75（均衡准确率 0.732，但会带来 20.3% 误拒答），
   需要按业务容忍度标定后才建议开启。
5. **重排默认是词面匹配（lexical）**：零依赖、快，但对同义改写不敏感；
   `cross_encoder` 精度更高，代价是下载模型与额外延迟（当前默认未启用）。
6. **Query 改写默认关闭**：`QUERY_REWRITE_ENABLED=false`，评测也是在关闭状态下跑的，
   开启后的收益尚未有实测数据。
7. **评测集规模有限（71 题）**：其中 `rag_pipeline` 类 MRR@10 仅 0.585，
   是该类问题（代码/概念细节）的已知短板。
8. **扫描件 PDF 解析为空**：没有 OCR，只有带文本层的 PDF 才能入库。
9. **BM25 用的是轻量 tokenizer**：不是专业中文分词器，专有名词/编号混排场景仍有优化空间。
10. **前端与容器加固未完成**：Markdown 渲染未加内容净化（`rehype-sanitize`）、
    容器未以非 root 运行、CSP / HSTS 未启用。

---

## 🗺️ Roadmap

**近 30 天（加固与标定）**

- 前端 Markdown 内容净化（`rehype-sanitize`）、非 root 容器、CSP / HSTS
- 按业务标定拒答阈值并默认启用分数维度拒答（用评测集验证误拒/漏拒的取舍）
- 前端路由懒加载 + ErrorBoundary，清理历史死代码
- 评测集扩充到 100~200 题，把 `rag_pipeline` 类短板纳入常规归因

**1~2 个季度（补齐产物）**

- Helm Chart 补全 `templates/`，让 `helm install` 真正可用
- Grafana 面板 + 告警规则（LLM 错误率、P95 延迟、token 成本）
- 向量库外置（Qdrant / pgvector），解除后端单副本约束并支持迁移 Job
- `cross_encoder` 重排作为可配置选项纳入评测对比，给出"默认值该选谁"的实测结论

**更远（平台化）**

- 组织级 / 用户级硬配额（表结构已就绪）
- 文档增量更新与重建索引（避免整库重跑）
- 评测结果进 CI 做回归门禁（指标下降即失败）

---

## 📈 Project Evolution

```text
RAG Demo（能问能答）
      ↓
Knowledge Chat（多格式解析 · 引用溯源 · 流式输出 · 多 Provider）
      ↓
平台化（权限 · 组织 · 审计 · 观测 · 工具 / Agent / 编排）  ← 当前 v1.0.1
      ↓
生产化（外置向量库多副本 · Helm/Grafana · 指标回归门禁 · 硬配额）
```

---

## 📜 版本历史

- **v1.0.1**（2026-09-30，持续更新至 2026-10-03）— Reality Audit 整改（Phase 1–3）：
  修复知识库越权读、占位密钥可上线、RBAC 全量 500、`api_keys` 迁移空桩等 P0 问题；
  统一错误契约；落地工具层（`kb_search` / `calculator`）、Agent、Workflow 的最小真实路径；
  补齐混合检索 + 重排 + 拒答 + 检索缓存与 RAG 评测；测试基线 **235 → 742 passed**。
- **v1.0.0** — RAG Pipeline、多 Provider、Prompt 管理、用户隔离。

---

## 📄 许可证

MIT
