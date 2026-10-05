# 智能知识库问答系统 — 架构文档

## 技术栈

| 层 | 技术 |
|---|------|
| Web 框架 | FastAPI (Python 3.12) |
| 数据库 | SQLite / PostgreSQL (SQLAlchemy async) |
| 向量存储 | ChromaDB |
| LLM | DeepSeek / Agnes（可扩展） |
| Embedding | SentenceTransformers (BAAI/bge-small-zh-v1.5) |
| 认证 | JWT |

## 项目结构

```
backend/app/
├── api/              REST API 路由
├── auth/             JWT 认证
├── core/             配置、日志
├── models/           SQLAlchemy DB 模型
├── services/
│   ├── llm/          LLM Provider
│   ├── embedding/    Embedding Provider + providers/
│   ├── retrieval/    Retriever + Reranker + Models
│   ├── chunking/     RecursiveChunker
│   ├── knowledge/    Pipeline + RuntimeConfig + Context
│   ├── tools/        Tool 层（kb_search / calculator + ToolRegistry）
│   ├── math_intent.py 数学意图唯一规则（Agent 规划器 / Workflow input_is_math / calculator 共用）
│   ├── agent/        Agent（确定性工具选择 + 受限执行 + 汇总）
│   ├── workflow/     Workflow（显式有序步骤 + 条件分支 + 状态传递 + 失败策略）
│   └── citation/     Citation + Builder
├── prompts/          Prompt Provider
└── storage/          DB + Vector Store
```

## 核心数据流

### 文档上传
```
DocumentService → KnowledgePipeline.process_document(ctx)
  └─ RuntimeConfig → ChunkerFactory → EmbeddingProviderFactory
     └─ parse → chunk → embed → vector_store
```

### 问答检索
```
ChatService → RetrievalPipeline.retrieve(question, kb_id)
  └─ RuntimeConfig → embed_query → VectorRetriever → score filter
     └─ CitationBuilder → context + sources + citations
```

### LLM 调用
```
ChatService → LLMProviderFactory.create(settings) → LLMProvider.chat()
  └─ UsageService.record(provider, model, tokens, latency)
```

### 工具调用（Tool Calling）
```
POST /api/tools/{tool_name}
  └─ ToolRegistry.invoke → asyncio.wait_for(BaseTool.run, TOOL_TIMEOUT_SECONDS)
     ├─ kb_search  → RetrievalPipeline.retrieve(query, kb_id)（含知识库归属校验）
     └─ calculator → ast.parse + 白名单求值（不使用 eval）；
                     参数是「1+2是多少」这类问句时，先按 math_intent 取出表达式
```
- 端点：`GET /api/tools`（清单 + JSON Schema）、`POST /api/tools/run`（按序多次调用，
  受 `TOOL_MAX_CALLS_PER_REQUEST` 约束，失败即停并保留已完成结果）、
  `POST /api/tools/{tool_name}/invoke`（单次调用，body 为 `{"arguments": {...}}`）。
- 错误契约：`ToolError` 继承 `AppError`，对外统一 `{"code","message","request_id"}`；
  原始异常只进日志，不泄漏内部细节。
- **上层编排**：Agent 在 `services/agent`（确定性工具选择 + 受限执行 + 汇总），
  Workflow 在 `services/workflow`（显式有序步骤 + `when` 条件分支 + `{{input}}` /
  `{{steps.<id>.output.*}}` 状态传递 + `on_error` 失败策略）；两者共用同一份
  `ToolRegistry`，**没有第二套工具执行**。编排上限（`WORKFLOW_MAX_STEPS` / 输入长度）
  由 `GET /api/workflows/limits` 暴露，前端据此提示而不是硬编码。
- **数学意图**：`services/math_intent.py` 是唯一实现（首尾措辞会被裁掉，
  `1+2是多少` → `1+2`），Agent 规划器、Workflow 的 `input_is_math`、
  calculator 的表达式提取都走它，避免"规划器认为不是、执行时又要求表达式"。
- **参数补齐口径**：`services/workflow/runner.py` 的 `INPUT_FILLED_ARGUMENTS` 声明
  "缺失时按本次输入取用"的参数（`calculator.expression` 借 `math_intent` 取表达式、
  `kb_search.query` 原样取用输入），写入口（`api/workflows.py`）据此只拦**不能**补齐的
  必填参数（`kb_search.knowledge_base_id` 属数据归属，不能替用户猜）→ 400；
  `GET /api/tools` 的 `parameters` 是标准 JSON Schema（规格在 `parameters.properties`），
  前端按它预填默认参数并为 kb_search 渲染知识库下拉。
