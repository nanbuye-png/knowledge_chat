# 智能知识库问答系统 — 架构文档

## 技术栈

| 层 | 技术 |
|---|------|
| Web 框架 | FastAPI (Python 3.12) |
| 数据库 | SQLite / PostgreSQL (SQLAlchemy async) |
| 向量存储 | ChromaDB |
| LLM | DeepSeek / Agens（可扩展） |
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
     └─ calculator → ast.parse + 白名单求值（不使用 eval）
```
- 端点：`GET /api/tools`（清单 + JSON Schema）、`POST /api/tools/run`（按序多次调用，
  受 `TOOL_MAX_CALLS_PER_REQUEST` 约束，失败即停并保留已完成结果）、
  `POST /api/tools/{tool_name}/invoke`（单次调用，body 为 `{"arguments": {...}}`）。
- 错误契约：`ToolError` 继承 `AppError`，对外统一 `{"code","message","request_id"}`；
  原始异常只进日志，不泄漏内部细节。
- **边界**：Agent 编排与 Workflow 引擎**未实现**（README 与前端页面均标注 Planned）。
