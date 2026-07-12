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