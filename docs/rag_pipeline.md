# RAG Pipeline 文档

## 检索增强生成流程

```
用户提问
  │
  ▼
ChatService.query_knowledge(question, kb_id)
  │
  ▼
RetrievalPipeline.retrieve(question, kb_id)
  │
  ├─ 1. KnowledgeRuntimeConfigService.resolve(kb_id)
  │      └─ retrieval_top_k (DB config 或 default 5)
  │
  ├─ 2. embedding_service.embed_query(question)
  │
  ├─ 3. VectorRetriever.retrieve(embedding, kb_id, top_k)
  │      └─ ChromaDB 向量检索
  │
  ├─ 4. Score filter (min_score = 0.3)
  │
  ├─ 5. CitationBuilder.build(chunks)
  │      └─ list[Citation] (document_id, filename, chunk_id, score)
  │
  ├─ 6. Context 组装
  │      └─ "[来源1] 文件名：...\n内容：..."
  │
  └─ 7. RetrievalResult(results, context, sources, citations)
```

## 关键组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `RetrievalPipeline` | `services/retrieval_pipeline.py` | 编排全流程 |
| `KnowledgeRuntimeConfigService` | `services/knowledge/runtime_config.py` | 解析 per-KB top_k |
| `VectorRetriever` | `services/retrieval/vector_retriever.py` | ChromaDB 查询 |
| `CitationBuilder` | `services/citation/builder.py` | 结构化引用 |
| `Reranker` (abstract) | `services/retrieval/reranker.py` | 预留重排序接口 |