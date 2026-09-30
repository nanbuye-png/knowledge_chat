# Knowledge Chat — Reality Audit（真实实现审计）

> **阶段**：Phase 0（Reality Audit）
> **性质**：只读审计。本阶段**未修改任何业务代码、未删除任何文件**。
> **审计日期**：2026-09-26
> **审计范围**：`backend/app/**`（146 个 Python 文件）、`frontend/src/**`（125 个 TS/TSX）、`backend/tests/**`、
> `alembic/**`、`docs/**`、`docker*`、`nginx/**`、`k8s/**`、`helm/**`、`monitoring/**`、`.github/workflows/**`
> **审计基线 commit**：`a689bf2`（branch `main`，工作区干净）
>
> **整改进度（2026-09-30 更新）**：本报告是审计当日的**快照**，正文不做追溯修改（保留实测证据）。
> 其中 P0/P1 项已在 Phase 1–3 修复并逐条提交，**逐项对应 commit 见文末 §14 整改进度表**。
> 判断"现在能不能用"请先看该表，不要按已修复的旧结论做决策。

---

## 0. 审计方法与实测证据

本报告不依赖主观判断。下表所有"实测"条目均为本次审计在本地实际执行并得到的结果。

| 手段 | 命令 / 方式 | 实测结果 |
|---|---|---|
| 测试套件全量运行 | `cd backend && python -m pytest -q -p no:cacheprovider` | **235 passed, 40 warnings in 11.80s** |
| 测试收集 | `python -m pytest --collect-only -q` | **235 tests collected** |
| 单文件收集 | `python -m pytest tests/test_sprint30_integration.py --collect-only -q` | **`no tests collected`**（该文件 0 用例入 CI） |
| 开发库只读查询 | `sqlite3.connect('file:knowledge.db?mode=ro', uri=True)` | 库存在；**26 张业务表**；**`api_keys` 表不存在** |
| Redis 缺陷复现 | `aioredis.from_url(..., protocol=1)` 后 `await ping()` | **`ConnectionError: protocol must be either 2 or 3`**（redis-py 8.0.1） |
| 迁移空桩确认 | 读取 `alembic/versions/d5660fbbb75e_add_api_keys_table.py` | `upgrade()` / `downgrade()` 均为 **`pass`** |
| 目录/文件存在性 | `Test-Path` | `evaluation/` **不存在**；`conftest.py`、`pytest.ini`、`pyproject.toml`、`.dockerignore` **均不存在** |
| Helm 模板 | 递归列目录 | `helm/knowledge-chat/templates/` **只有 `_helpers.tpl`**，0 个资源模板 |
| 监控产物 | 递归列目录 | `monitoring/grafana/` **只有 `.gitkeep`** |
| 路由真实性 | grep `prefix="/api/agents"` / `"/api/workflows"` | **后端 0 命中**（Agent/Workflow/Tools 后端不存在） |
| 埋点调用点 | grep `usage_service.record(` / `track_request(` / `track_llm_call(` | **生产代码 0 调用点**（仅定义与文档提及） |
| 已有文档交叉验证 | 复核 `docs/INTERVIEW_GUIDE.md` 逐条 | 部分条目**已过时**，见 §10 |

### 状态标记定义

| 标记 | 含义 |
|---|---|
| **COMPLETE** | 完整实现，主链路真实可用 |
| **PARTIAL** | 部分实现（主链路可用但存在真实缺口，或仅覆盖部分场景） |
| **SCAFFOLD** | 只有框架/抽象层，未被业务使用或未接通 |
| **MISSING** | 不存在 |
| **DOC_ONLY** | 文档/前端宣称有，代码无对应实现 |

---

## 1. 状态总览

| 域 | COMPLETE | PARTIAL | SCAFFOLD | MISSING | DOC_ONLY |
|---|---|---|---|---|---|
| RAG | Parser、Chunking、VectorStore、VectorRetriever、ContextBuilding、LLMGeneration | Embedding、Citation | — | — | — |
| AI | Provider、Streaming、Prompt | ErrorHandling | — | — | TokenUsage |
| Agent | — | — | — | Agent / Workflow / Tools（后端） | 前端页面 + `api/agents.ts`、`api/workflows.ts` |
| Engineering | — | Logging、Async | Redis、Monitoring | Retry、Idempotency、Metrics 写入 | — |
| Security | — | Authentication、Authorization、RBAC | — | — | — |
| Deployment | DockerCompose、CI/CD | Docker、Kubernetes、Nginx | Helm | — | — |
| Testing | — | Unit、Integration | — | RAG Tests、API Tests | — |

### 核心结论

1. **RAG 检索主链是真实可用的**：解析 → 切分 → 向量化 → 余弦检索 → 阈值过滤 → 上下文拼装 → 流式生成，
   每一环都有具体实现，可在面试中逐行讲解。
2. **"Advanced RAG" 全部为零**：Query Rewrite、Hybrid Retrieval、Reranker、Context Score Threshold、
   Abstention、答案级 Citation 校验 —— **一项都没有实现**。
3. **Evaluation 为零**：无评测集、无 Recall@K / MRR、无任何评测脚本。
4. **Ingestion Engineering 为零**：无异步入库（同步阻塞请求）、无重试、无幂等去重。
5. **Observability 是断链空壳**：`/metrics` 未注册、埋点零调用、`llm_usages` 无写入端。
6. **README 与代码的偏差集中在"企业级附加能力"**：Agent/Workflow/Tools、可观测性、ACL、Helm、Redis 缓存
   —— 均为 DOC_ONLY 或 SCAFFOLD（详见 §9）。
7. **测试"绿"具有误导性**：235 个用例全部通过，但存在**整个文件 0 收集**、大量 mock-only 用例、
   恒真断言、且 **0 个 HTTP 层测试**（详见 §8）。

---

## 2. RAG 域（逐项）

### 2.1 Document Parser

```text
功能：多格式文档解析
状态：COMPLETE
代码位置：backend/app/services/parser/{factory,base,pdf_parser,docx_parser,doc_parser,
          markdown_parser,text_parser,csv_parser,xlsx_parser}.py
当前实现：
  - ParserFactory.get_parser(path) 按扩展名分派：pdf / docx / doc / md / txt / csv / xlsx
  - 各解析器返回 {"filename", "content", "metadata"}
  - PDF 用 PyMuPDF 逐页 get_text()，页号以 "[第N页]\n{text}" 形式写入 content（pdf_parser.py:42）
存在问题：
  1) [功能性] PDF 无 OCR，扫描件解析结果为空；表格按文本流顺序还原，结构丢失
  2) [阻塞 Phase 1 §5.5] 页号只存在于 content 文本里，**未进入 chunk metadata**
     → Citation 无法追溯到 page；section / heading 层级完全未抽取
  3) [工程性] 解析无超时保护、无重试，大文件在请求线程内同步阻塞
改进建议：
  - Parser 返回值扩展为 {"content", "metadata": {"pages": n, "sections": [...]}}
  - 把 page/section 透传到 vector_store 的 chunk metadata，供 §5.5 Citation 使用
  - 为大文件解析加超时与后台化（与 §7.1 异步入库一并解决）
优先级：P1
```

### 2.2 Chunking

```text
功能：文本切分（段落感知 + 重叠）
状态：COMPLETE（实现质量高，可作为面试亮点）
代码位置：backend/app/services/chunking/{base,factory,recursive_chunker}.py
          + 遗留副本 backend/app/utils/text_chunker.py（同一算法的第二份拷贝）
当前实现：
  - RecursiveChunker 四步法：
    ① 正则占位保护时间/日期/金额/百分比（recursive_chunker.py:23-30, 84）
    ② 只折叠空格与 Tab、保留 \n（:88）
    ③ 按双换行切段逐个并入，溢出时在 target±100 窗口内从右往左找句末标点（:110-139）
    ④ 按 chunk_overlap 回退形成重叠（:163），最后过滤长度 ≤10 的碎片（:189）
  - 明确禁止把 ": " 当切分点（:116-118），避免破坏 "08:00-12:00"
  - 每 KB 可通过 KnowledgeConfig 覆盖 chunk_size / chunk_overlap
存在问题：
  1) [设计] 按字符数切而非 token（中文 500 字符约 300~400 token，中英混排长度语义不一致）
  2) [设计] 无 heading / section 感知切分，与 §2.1 的 section 缺失互为因果
  3) [卫生] utils/text_chunker.py 作为死副本存在，会误导后续维护者
改进建议：
  - 保留现有算法（不要重写）
  - 增加 heading-aware 边界（在 section 标题处优先切分）
  - 删除 utils/text_chunker.py 死副本
优先级：P2
```

### 2.3 Embedding

```text
功能：文本向量化（本地 + 云 Provider）
状态：PARTIAL
代码位置：backend/app/services/embedding/{base,factory}.py
          backend/app/services/embedding/providers/{bge,jina,openai,voyage,default}.py
          backend/app/services/embedding_service.py（向后兼容垫片）
当前实现：
  - EmbeddingProvider 抽象基类 + EmbeddingProviderFactory 注册表（bge/jina/openai/voyage）
  - bge → SentenceTransformer 本地加载；加载失败降级到 transformers 原生实现
  - 全部失败 → **随机向量兜底**（providers/default.py:190-196），且 _initialized 置 True
  - 归一化向量（normalize_embeddings=True / F.normalize）
存在问题：
  1) [P0-2 阻塞评测] EMBEDDING_DIM 默认 768（core/config.py:107），
     而 BAAI/bge-small-zh-v1.5 实际输出 512 维 → 兜底向量维度与真实向量不一致
  2) [P0-2 阻塞评测] 随机向量是"静默错误"：向量化失败既不抛错也不把文档标记 FAILED，
     无意义的随机向量会被写入向量库并参与检索 → 污染评测数据与线上结果
  3) [可用性] jina/openai/voyage 已在工厂注册，但 config.py 没有对应 API Key 字段，
     一旦选用必然缺 key（不可达路径）
  4) [效果] 中文 bge 检索缺少指令前缀（「为这个句子生成表示以用于检索相关文章：」）→ 召回率偏低
  5) [性能] 无分批、无重试、无速率控制（大文档一次性 embed_documents）
  6) [架构] 所有 KB 共用一个 COLLECTION_NAME="documents"，但 embedding_model 可按 KB 配置
     → 不同维度/语义空间的向量混存同一 collection
改进建议：
  - 兜底策略改为**显式失败**（raise → 文档状态 FAILED + error_message），禁止随机向量入库
  - 修正 EMBEDDING_DIM 与 bge-small-zh 一致（512），或从模型动态探测
  - bge query 侧补检索指令前缀（document 侧不加）
  - 云 Provider 的 API Key 落到 settings 或从工厂下架（不做不可达路径）
  - collection 按 embedding 模型/维度分集合，或在 metadata 中加 model 字段并在检索时过滤
优先级：P0（1、2、6 直接影响 Phase 2 评测可信度）
```

### 2.4 Vector Store

```text
功能：向量存储与相似度检索
状态：COMPLETE
代码位置：backend/app/storage/vector_store.py
当前实现：
  - chromadb.PersistentClient + collection "documents"（hnsw:space=cosine）
  - add_document_chunks(ids=f"{document_id}_{i}", documents, embeddings, metadatas)
    metadata = {document_id, filename, chunk_index, text[:500], knowledge_base_id, user_id}
  - search(query_embedding, top_k, knowledge_base_id) → where {"knowledge_base_id": {"$eq": id}}
    score = 1 - cosine_distance（:159）
  - 删除：delete_document / delete_knowledge_base / delete_user
存在问题：
  1) [性能+安全] 生产路径打诊断日志：写入后 collection.get() 回读 metadata（:93, 105-107）；
     **每次检索都 peek(limit=3) 并打印样本 metadata（:134-139）** → 含其他用户文档片段入日志
  2) [正确性] get_document_chunk_count 返回 collection.count()（全库计数），语义错误（:220-231）
  3) [安全] search 仅按 knowledge_base_id 过滤，**未按 user_id 过滤**（授权未下沉到数据层）
  4) [架构] 本地 PersistentClient + K8s replicas:2/HPA → 多副本向量数据分叉
改进建议：
  - 诊断日志降为 DEBUG 且由开关控制；移除检索路径的 peek
  - 修 get_document_chunk_count 语义（按 document_id 过滤计数）
  - 把 user_id 下沉到 where 条件（默认安全）
  - 多副本问题在 README/部署文档中显式标注限制（不擅自更换 Vector DB）
优先级：P1（3、4）、P2（1、2）
```

### 2.5 Retriever / Retrieval Pipeline

```text
功能：检索编排（embed → search → 过滤 → 引用 → context）
状态：COMPLETE
代码位置：backend/app/services/retrieval/{base,vector_retriever,factory}.py
          backend/app/services/retrieval_pipeline.py
当前实现：
  - RetrievalPipeline.retrieve(question, knowledge_base_id, top_k, min_score)
    ① 解析 top_k（调用方 → KnowledgeRuntimeConfig → 默认 5）
    ② embedding_service.embed_query(question)
    ③ RetrieverFactory.create().retrieve(embedding, kb_id, top_k)
    ④ 阈值过滤 r["score"] >= min_score
    ⑤ CitationBuilder.build(relevant)
    ⑥ 拼 context（"[来源i] 文件名：x (段落n)\n内容：…"）与 sources
    ⑦ 返回 RetrievalResult(results, context, sources, citations, has_results)
存在问题：
  1) [阻塞 Phase 1] BaseRetriever.retrieve 签名只接收 embedding，**不接收原始 query 文本**
     （retrieval/base.py:53）→ BM25 / Hybrid 需要 query，必须演进签名
  2) [阻塞 Phase 1] min_score=0.3 硬编码为类属性（retrieval_pipeline.py:44），非配置项
  3) [死抽象] RetrievalProvider 抽象类定义了但无任何实现与调用
  4) [死逻辑] RetrieverFactory.create() 无任何分支，永远返回 VectorRetriever（无配置驱动）
改进建议：
  - 扩展签名：retrieve(embedding=..., knowledge_base_id=..., top_k=..., query: str | None = None)
    保留原位置参数以兼容现有调用与测试
  - 阈值 / 权重 / rerank top_k / abstention 阈值全部进 settings（默认）+ KnowledgeConfig（覆盖）
  - 清理无人使用的 RetrievalProvider 抽象
优先级：P0-3（Phase 1 的前置改造）
```

### 2.6 Citation

```text
功能：答案引用标注与溯源
状态：PARTIAL
代码位置：backend/app/services/citation/{models,builder}.py
          backend/app/services/retrieval_pipeline.py:118, 129-134
当前实现：
  - CitationBuilder.build(chunks) → list[Citation(document_id, filename, chunk_id, score, metadata)]，
    按 score 降序
  - 写入 RetrievalResult.citations
  - context 中带 "[来源1] 文件名：… (段落N)"，由 Prompt 要求模型据此标注
存在问题：
  1) [关键] RetrievalResult.citations **零消费**：chat_service 只取 .sources
     （chat_service.py:165-173 与 :280）→ 结构化引用算了但不用，从未到达前端
  2) [阻塞 §5.5] Citation 模型无 page / section 字段 → 无法满足
     document_id / chunk_id / source / page / section 的完整追溯要求
  3) 引用由 Prompt 引导模型自行标注，**无代码级一致性校验** → 模型可以生成不存在的引用
  4) [一致性] 文档删除后，已落库的 assistant 消息中的 sources 无失效标记
改进建议：
  - citations 一路贯通：RetrievalResult → ChatService → SSE 控制帧 → 前端（与 sources 并行下发）
  - Citation 增加 page / section（依赖 §2.1 的解析元数据透传）
  - 增加"引用 ∈ 本次最终 context"的代码级校验，禁止模型自造引用
  - 文档删除时对历史消息标注引用失效（不删除数据，只标记）
优先级：P1（对应 Phase 1 §5.5）
```

### 2.7 Context Building

```text
功能：把检索结果拼装为 LLM 可用上下文
状态：COMPLETE
代码位置：backend/app/services/retrieval_pipeline.py:121-134
当前实现：
  - 每条：f"[来源{i+1}] 文件名：{filename} (段落{chunk_index})\n内容：{text}"
  - "\n\n".join 后传给 Prompt Provider
存在问题：
  1) 分数阈值硬编码（0.3），不可配置
  2) 无 token 预算裁剪（chunk 数 × chunk_size 可能超出模型上下文）
  3) 无同文档去重 / 聚合（同一文档的相邻 chunk 会重复占位）
改进建议：
  - 阈值可配置（Phase 1 §5.4）
  - 按 token 预算截断（可配）
  - 同文档多 chunk 聚合与去重
优先级：P1
```

### 2.8 LLM Generation

```text
功能：基于上下文的答案生成（含流式）
状态：COMPLETE
代码位置：backend/app/services/chat_service.py
          query_knowledge(:108) / chat(:184) / stream_chat(:217) / stream_query_knowledge(:251)
当前实现：
  - RAG：system(RAG prompt) + history[-10:] + user → LLM provider chat/stream
  - temperature：RAG 0.3、闲聊 0.7；max_tokens=2000
  - 流式：先 yield 控制帧 {"type":"sources"}，再 yield token
存在问题：
  1) temperature / max_tokens 硬编码，不可按 KB 或按请求配置
  2) RAG 与闲聊共用同一个 LLM provider 实例，无 per-request 模型覆盖
  3) 异常分支把 str(e) 直接拼进用户可见回答（chat_service.py:180）→ 可能泄露内部信息
改进建议：生成参数进配置（settings + KnowledgeConfig 覆盖）；异常只回固定用户文案，细节进日志
优先级：P2
```

---

## 3. AI 域（逐项）

### 3.1 LLM Provider

```text
功能：多 Provider 抽象与工厂
状态：COMPLETE（DB 驱动路径为 PARTIAL）
代码位置：backend/app/services/llm/{base,factory,deepseek_provider,agens_provider}.py
          backend/app/services/model_registry.py
当前实现：
  - LLMProvider 抽象基类；_PROVIDERS 注册表（deepseek / agens）
  - LLMProviderFactory.create(settings) 按 settings.LLM_PROVIDER 创建
  - create_with_name / create_from_model / create_from_registry(DB)
  - 均基于 OpenAI 兼容协议复用 AsyncOpenAI
存在问题：
  1) [重复] deepseek_provider.py 与 agens_provider.py 近逐字重复；
     仅 agens 版有 `if not chunk.choices: continue` 空 choices 保护，deepseek 版没有
  2) [DOC_ONLY 关联] create_from_registry() **零调用**，聊天永远读 .env
     → Model Registry / AI 配置中心页面改了不生效
  3) [配置] 代理/超时参数集中在工厂 _build 里按 provider 名硬编码分支
改进建议：
  - 抽 OpenAICompatibleProvider 基类，消除两份重复，并把空 choices 保护下沉到基类
  - 明确 Model Registry 是否接入主链路：接入则用 create_from_registry，不接入则在 README 标 Planned
优先级：P2
```

### 3.2 Streaming（SSE）

```text
功能：流式输出
状态：COMPLETE（协议健壮性 PARTIAL）
代码位置：backend/app/api/chat.py:138、backend/app/api/knowledge_query.py:165
          backend/app/services/chat_service.py:251-319
          frontend/src/api/knowledge.ts:27-124
当前实现：
  - StreamingResponse + media_type="text/event-stream" + X-Accel-Buffering: no
  - 信封：data: {"token": "<控制帧 JSON 或 纯文本 token>"}
  - 控制帧：{"type":"sources"|"no_result"|"error"}；结束：data: [DONE]
  - 前端原生 fetch + ReadableStream + AbortController，处理 TCP 半行（buffer.split）
存在问题：
  1) [协议] 靠"第二层 JSON.parse 是否抛异常"区分控制帧与正文：
     若正文 token 恰好是合法 JSON（如 "1000"、"2026"、'{"a":1}'），
     inner.type 为 undefined → 三个分支都不命中 → **token 被静默丢弃**（knowledge.ts:87-108）
  2) [上下文] 流式接口前端不传 history（knowledge.ts:45 请求体无 history），
     后端 history 默认 [] 且不从 messages 表回读 → **流式下多轮上下文实际丢失**
  3) [安全] 前端 api/client.ts 把 AxiosError 换成裸 Error → 401 不跳登录页
改进建议：
  - 显式类型字段：{"type":"token","data":"1000"}，消除形态判类型
  - 后端从 messages 表回读 history，不信任客户端传值
  - 前端补 401 拦截跳登录
优先级：P1
```

### 3.3 Prompt

```text
功能：提示词管理与版本化
状态：COMPLETE
代码位置：backend/app/prompts/{base,default,database,factory,resolver}.py
          backend/app/api/prompt_template.py、prompt_version.py
          backend/app/core/prompt_cache.py
当前实现：
  - BasePromptProvider 抽象；DefaultPromptProvider 提供 system / rag / chat 三类模板
  - DatabasePromptProvider + resolve_prompt_provider(session) 实现 DB 模板优先
  - 模板 CRUD + 版本表 + 回滚接口
存在问题：
  1) RAG 提示词只要求"仅根据参考知识回答 + 无信息则说明"，**未要求结构化引用标注**
     与"拒答/Abstention"的明确契约 → 与 §5.5 / §5.6 目标有差距
  2) core/prompt_cache.py 的 get/has/clear **零调用**（只写不读）
  3) 前端 `/prompt-templates/{id}/compile` 端点后端 404
改进建议：
  - RAG Prompt 增加"引用必须来自给定来源编号"与"无依据时明确拒答"的显式约束
  - 决定 prompt_cache 的处置：接入或删除
优先级：P2
```

### 3.4 Token Usage

```text
功能：Token 用量采集与统计
状态：DOC_ONLY（写入端完全缺失）
代码位置：backend/app/services/usage_service.py:13
          backend/app/models/llm_usage.py、backend/app/api/usage.py
          frontend/src/pages/{admin/UsageDashboardPage,monitoring/TokenAnalyticsPage,AIMetricsPage}.tsx
当前实现：
  - llm_usages 表、UsageService.record()/get_user_stats()/get_recent()、/api/usage/* 接口、
    前端 4 个分析页面全部存在
存在问题：
  1) [实测] grep `usage_service.record(` → **生产代码 0 调用点** → llm_usages 永远为空
  2) 前端 Token 分析 / AI 指标页面恒显示 0
  3) Prompt/Completion token 数未从 provider 响应中采集（provider 也未透出 usage）
改进建议：
  - 在 ChatService 的每个 LLM 调用点接 usage_service.record()
  - Provider 层透出 usage（流式需累计/估算），与 Phase 3.6 的 request 级观测统一
优先级：P1（Phase 3.6 依赖）
```

### 3.5 Error Handling

```text
功能：AI 调用错误处理
状态：PARTIAL
代码位置：backend/app/services/chat_service.py:177-182, 247-249, 313-319
          backend/app/main.py:131-144、backend/app/core/exceptions.py
当前实现：
  - 检索失败 → SSE error 控制帧；LLM 失败 → 返回/流式输出错误文案
  - 全局 AppError / HTTPException / Exception 三层处理器
存在问题：
  1) [韧性] 无 retry、无退避、无超时分类（LLM 超时与 4xx 同等对待）
  2) [可观测] main.py:137 用 logger.error(f"...{exc}") **不打堆栈**
  3) [信息泄露] chat_service.py:180 把 str(e) 直接拼进用户可见回答
  4) [契约] 全局异常返回 {"code","message"}，而 HTTPException 处理器/Middleware 返回
     {"detail":...} → 前端需要两套解析
改进建议：引入统一 retry 工具（可配次数/退避）；异常统一为单一错误契约；用户文案与内部错误解耦
优先级：P1
```

---

## 4. Agent / Workflow / Tools

```text
功能：Agent / Workflow / Tools 平台框架
状态：MISSING（后端） + DOC_ONLY（前端与 README）
代码位置：
  后端：**不存在**
        - app/api/ 下无 agents.py / workflows.py / tools.py
        - 无对应 models / services
        - 路由 grep：prefix="/api/agents"、"prefix=\"/api/workflows\"" → 0 命中
  前端：frontend/src/api/agents.ts、frontend/src/api/workflows.ts（请求 /agents、/workflows → 404）
        frontend/src/pages/ai/AgentManagementPage.tsx:19 → 文案"AI Agent 管理（后端能力待实现）"，
          且 :5-7 使用 hardcoded placeholderAgents 假数据渲染表格
        frontend/src/pages/ai/WorkflowManagementPage.tsx:22-23 → 文案"Workflow 功能待后端支持"
          "当前系统无 Agent/Workflow/Tool 后端 API"
        frontend/src/pages/ai/ToolRegistryPage.tsx → 纯静态页面
        frontend/src/pages/platform/agents/AgentStudioPage.tsx（15KB）、
          platform/workflows/WorkflowStudioPage.tsx（16KB）→ 会**真实调用** listAgents/listWorkflows/execute
  测试：backend/tests/test_sprint31_ai_enhancement.py:309-364 的 TestToolCalling、
        TestWorkflow、TestAgent、TestAIPipeline
        **在测试文件内部自定义了 Tool / ToolRegistry / Workflow / Agent 玩具类**，
        与生产代码无任何关系；test_tool_validation 只断言本地 dict
当前实现：仅前端页面与 API 客户端空壳
存在问题：
  1) README.md:61 宣称"Agents / Workflows / Tools：AI Agent 平台框架" → DOC_ONLY
  2) 测试内的玩具实现会让人误判"已实现"（测试绿 ≠ 功能在）
  3) AgentStudioPage / WorkflowStudioPage 会真实发请求并 404
改进建议：
  - Phase 4 前先修正 README 措辞为 Planned，并在前端空壳页面统一"Planned"标注
  - 若实现，只做一个真实场景（KB 检索 + Calculator），必须有 Tool 选择逻辑、
    Tool 超时、最大执行次数、失败处理（与计划 §10 一致）
  - 删除或重写 test_sprint31 中与生产无关的玩具用例
优先级：P3（Phase 4）
```

---

## 5. Engineering 域

### 5.1 Async Ingestion

```text
功能：文档异步入库
状态：SCAFFOLD
代码位置：backend/app/services/tasks/{base,local_worker,document_task,__init__}.py
          backend/app/services/factory.py:106（init_providers）
          backend/app/services/document_service.py:29-98（upload_document）
当前实现：
  - TaskBase 抽象（PENDING/RUNNING/SUCCESS/FAILED + to_dict）
  - LocalWorker（内存 _tasks dict，submit/_execute/get_task/list_tasks）
  - submit_task() 门面 + get_worker()/set_worker() 注入点
  - 上传路径：校验 → 落盘 → 建 Document(status=PROCESSING) → **在请求内同步** parse→chunk→embed→store
存在问题：
  1) [实测] `submit_task(` **零业务调用**；上传仍同步阻塞在请求内
     → 50MB PDF 的解析+嵌入会占住该请求数分钟
  2) [占位] DocumentEmbeddingTask.run() 是 TODO：不调用 EmbeddingService，
     返回硬编码 chunks_count = len(content)//500 + 1（document_task.py:36-41）
  3) [执行模型] LocalWorker._run_async 在已有 running loop 时用 asyncio.ensure_future
     → 任务绑定在**请求的事件循环**上，请求结束可能被取消；无线程/队列/持久化
  4) [状态机] DocumentStatus 只有 PROCESSING/COMPLETED/FAILED，无 PENDING
     （models/document.py:13-16）；无 started_at/finished_at
改进建议：
  - DocumentStatus 增加 PENDING；上传改为落盘+建记录(PENDING)后立即返回 202 + document_id
  - Worker 改为独立执行（独立线程/loop 或队列），任务状态落 DB 而非内存 dict
  - 前端轮询 /api/documents/{id}/status（该接口与前端轮询已存在，可直接对接）
优先级：P0-4（Phase 3 主体）
```

### 5.2 Retry

```text
功能：失败重试与退避
状态：MISSING
代码位置：无（全仓库无 retry / backoff / tenacity 用法）
当前实现：Embedding API、LLM API、Parser、VectorStore 全部单次调用，失败即失败
存在问题：
  1) 无 retry 策略；无 retry_count / last_error 字段（Document 只有 error_message）
  2) 无最大重试上限概念（因为根本没有重试）
改进建议：
  - 统一 retry 工具（max_retries / backoff / 可重试异常白名单，全部可配）
  - Document 表补 retry_count / last_error / updated_at（updated_at 已有），
    达到上限 → FAILED
  - 明确区分"可重试"（网络/5xx/超时）与"不可重试"（4xx/解析失败/空内容）
优先级：P1（Phase 3 §7.2）
```

### 5.3 Idempotency

```text
功能：重复上传 / 重复处理的幂等
状态：MISSING
代码位置：backend/app/services/document_service.py:54（每次生成新 uuid）、models/document.py
当前实现：无任何去重；同一文件重复上传会得到不同 document_id 与不同向量 id 前缀
存在问题：
  1) 重复上传 → 重复 chunk、重复 embedding、重复向量（id = f"{document_id}_{i}" 不覆盖旧值）
  2) 无 SHA-256 文件指纹字段，无唯一约束
  3) 重复处理会浪费 Embedding 算力与 LLM/向量存储配额
改进建议：
  - 上传时计算 SHA-256(file)，写入 Document.file_hash（加索引）
  - 同 KB 内已存在相同 hash → 复用/跳过，并在 API 响应中明确返回 skipped 语义
  - 明确"不破坏已有 Document"：只返回既有记录的引用，不覆盖、不删除
优先级：P1（Phase 3 §7.3）
```

### 5.4 Redis

```text
功能：Redis 缓存 / 限流支撑
状态：SCAFFOLD（且当前**实际不可用**）
代码位置：backend/app/core/redis.py:12-40
          backend/app/services/cache/{base,memory_cache,redis_client,cache_service}.py
          backend/app/services/rate_limit_service.py、core/rate_limit.py、middleware/rate_limit.py
          docker-compose.yml:28-42（redis 服务）
当前实现：
  - BaseCache 抽象 + MemoryCache + RedisCache（JSON 序列化 + TTL + 降级）
  - CacheService：三类 key（prompt_template / knowledge_config / session）+ get_or_set + clear_all
  - 限流：core/rate_limit.py（路由依赖）+ middleware/rate_limit.py（Redis INCR/EXPIRE）
    + services/security/rate_limiter.py
存在问题（含实测）：
  1) [实测 P0-1] core/redis.py:30 传 `protocol=1` 非法值 →
     本地实测 `await client.ping()` 抛 `ConnectionError: protocol must be either 2 or 3`（redis-py 8.0.1）
     → get_redis() 恒返回 None → 中间件限流 **fail-open（永久放行）**
  2) [实测] `init_providers()` **从不在 lifespan 调用**（仅测试调用）→ CACHE_BACKEND=redis 永远不生效
  3) [实测] CacheService **零业务引用**（仅 test_cache_integration.py 引用）
  4) [限流] middleware 读 request.state.user_id / role，而全仓库从未给 request.state 赋值
     → 按用户限额从未生效；/api/chat/* 与 /api/knowledge/query/stream 无限流依赖（加 /stream 即绕过）
  5) [安全] X-Forwarded-For 取首值（nginx 用 $proxy_add_x_forwarded_for 保留客户端伪造值）
     → 可伪造 IP 绕过登录限流与账号锁定
改进建议：
  - 修 protocol=2；lifespan 内调用 init_providers()
  - 把 Redis 用于**真实场景**（候选：检索结果缓存 / 限流），并写清"为什么用/缓存什么/Key 设计/TTL/失效策略"
  - 合并三套限流实现为一套；补齐 /chat/* 与 /query/stream 的限流依赖
优先级：P0-1（当前限流等同不存在）
```

### 5.5 Logging

```text
功能：日志
状态：PARTIAL
代码位置：backend/app/core/logging.py、backend/app/main.py:43-91、各 service
当前实现：loguru；控制台 + 文件输出；启动打印 Provider/模型/DB/向量/嵌入 摘要；
          嵌入自检 check_llm_config()
存在问题：
  1) [安全] vector_store.py:93,105-107 每次写入回读并打印完整 metadata；
     :134-139 **每次检索 peek(3) 并打印样本 metadata**（含其他用户文档片段）
  2) [安全] main.py:88 把含 PostgreSQL 密码的完整 DATABASE_URL 打进日志
  3) [排障] main.py:137 全局异常 logger.error(f"...{exc}") **不打堆栈**
  4) [噪声] recursive_chunker / knowledge pipeline 对每个 chunk 打 DEBUG 全量内容
改进建议：
  - 诊断日志降级为 DEBUG 并用开关控制；移除检索路径 peek
  - 敏感连接串脱敏；异常统一 logger.exception
优先级：P1
```

### 5.6 Monitoring / Metrics

```text
功能：Prometheus 指标 + Grafana + 业务指标（Token/AI 指标/错误追踪）
状态：SCAFFOLD
代码位置：backend/app/services/metrics.py（router + REQUEST_COUNT/REQUEST_LATENCY/ERROR_COUNT/
          LLM_TOKENS/LLM_COST/LLM_LATENCY/ACTIVE_USERS/TOTAL_* /CACHE_HITS/CACHE_MISSES）
          backend/app/main.py:148-166（路由注册处）
          monitoring/prometheus/prometheus.yml、monitoring/grafana/（仅 .gitkeep）
          backend/app/api/health.py
存在问题：
  1) [实测] metrics router **未在 main.py 注册**（include_router 列表无它）→ /metrics 404
  2) [实测] track_request / track_llm_call **零调用点**
  3) prometheus.yml 抓取 backend:8000/metrics，该路由不存在 → target down
  4) Grafana 目录只有 .gitkeep；compose / k8s 中无 Prometheus、Grafana 服务载体
  5) [实测] /api/health 硬编码 "status": "healthy"（api/health.py:22-29），不探测 DB/Redis/向量库
     → Docker/K8s 探针失去意义
  6) [性能] system_monitor 用 psutil.cpu_percent(interval=1) 在 async 处理器内同步阻塞 1 秒
改进建议：
  - 注册 metrics router；加中间件调 track_request；LLM 调用点调 track_llm_call
  - /api/health 改为真实依赖探测（DB ping / 向量库 count / Redis 可选）
  - Phase 3.6 的请求级观测（request_id/trace_id + 分段耗时）落地时统一复用
优先级：P1（Phase 3.6 基础）
```

---

## 6. Security 域

### 6.1 Authentication

```text
功能：JWT 认证 + API Key
状态：PARTIAL
代码位置：backend/app/auth/{jwt,security,deps,api_key}.py
          backend/app/api/auth.py、backend/app/services/auth/{token_service,rbac_service}.py
          backend/app/models/{token_blacklist,user_session,api_key}.py
当前实现：
  - JWT：HS256 / jti / exp / role / 算法白名单
  - bcrypt 密码哈希（cost=12，UTF-8 72 字节截断，依赖锁定 bcrypt<4.1）
  - TokenBlacklist（jti unique）+ UserSession（token_hash / revoked_at）
  - 登录防爆破（5 次失败锁 15 分钟）+ 防用户名枚举（同一错误文案）
  - API Key：160bit 随机、只存 SHA256、明文只返回一次、撤销带属主校验
存在问题：
  1) [P0 安全] SECRET_KEY 默认公开值（core/config.py:124
     = "knowledge-chat-secret-key-change-in-production"），.env.production 与 compose 也是占位串
     → 按仓库现状部署，任何人都可签发 ROOT token
  2) [P0 安全] get_current_user 不校验 is_active / deleted_at（auth/deps.py:58-59）
     → 软删除/禁用用户凭未过期 JWT（默认 24h）继续读写全部业务数据
  3) [功能不可用] API Key 通道实际不可达（api/chat.py:27-35 的依赖组合 + auth/deps.py:23-28）
  4) [P0 正确性] naive/aware datetime 混用：users.locked_until 读回为 naive，
     代码用 datetime.now(timezone.utc) 比较 → **账号锁定一旦触发，登录即 500**；
     同类问题导致 /api/auth/sessions、/api/admin/sessions、在线用户列表 500
  5) [数据-实测] 迁移 d5660fbbb75e 是空桩 → 全新部署后 api_keys 表不存在
     （开发库实测 26 张表，无 api_keys）
  6) [凭证撤销] 删除/禁用用户不撤销 session 与 API Key；logout 只写黑名单不撤 session
  7) [暴露面] /docs、/redoc、/openapi.json 未按 ENVIRONMENT 关闭
改进建议（最小止血）：
  - SECRET_KEY 使用默认值时 fail-fast 拒绝启动
  - get_current_user 增加 is_active / deleted_at 过滤；删用户时撤销 session + API Key
  - 统一 datetime 策略（全部 timezone=True 或统一 naive UTC）
  - 补齐 api_keys 建表 revision + alembic/env.py 导入全部模型
  - 生产环境关闭 /docs
优先级：P0（安全，建议纳入 Phase 1 一并止血）
```

### 6.2 Authorization

```text
功能：资源级授权（知识库访问控制）
状态：PARTIAL
代码位置：backend/app/api/knowledge_query.py:85-86, 131-136
          backend/app/services/document_service.py、storage/vector_store.py:129-146
当前实现：
  - 无 conversation_id 时调用 verify_knowledge_base_access（KB.user_id == current_user.id）
  - Document / KnowledgeBase 的 CRUD 均带 user_id 过滤
存在问题：
  1) [P0 越权 IDOR] stream_query_knowledge：当请求带 conversation_id 时
     **跳过 KB 归属校验**（knowledge_query.py:131 仅在 conversation_id is None 时校验）
     → 通过 conversation_id 可越权检索他人知识库
  2) [纵深防御] 向量检索只按 knowledge_base_id 过滤，未按 user_id 过滤
     → 一旦上层授权漏检，数据层无兜底
改进建议：
  - 从 conversation_id 反查会话并校验 conv.knowledge_base_id == request.knowledge_base_id
  - 或统一走 verify_knowledge_base_access（不再依赖 conversation_id 分支）
  - user_id 下沉到向量 where 条件（默认安全）
优先级：P0（OWASP A01 Broken Access Control）
```

### 6.3 RBAC

```text
功能：三级角色 + 细粒度权限码
状态：PARTIAL
代码位置：backend/app/core/{rbac,permissions,roles}.py
          backend/app/services/auth/rbac_service.py、backend/app/api/admin/*.py
当前实现：
  - ROOT / ADMIN / USER 三级角色；permissions / roles / role_permissions / user_roles 表
  - require_admin_or_root / require_role / require_permission 依赖工厂
  - 启动时幂等初始化默认角色权限
存在问题：
  1) [P0] has_permission 的查询 join 缺 roles 表 → ADMIN 访问整个管理后台 500
  2) [死功能] user_roles 表无任何写入方 → 细粒度权限码实际从未启用
  3) [死代码] require_role / require_admin / require_authenticated 等工厂无调用点
  4) [策略不一致] PATCH /users/{id}/role 允许设为 ROOT（admin/users.py:349），
     而创建用户只允许 {USER, ADMIN} → ADMIN 可把任意用户提权为 ROOT
改进建议：修 RBAC join；明确 user_roles 写入路径（或标注 Planned）；统一角色变更策略
优先级：P0（1、4）
```

---

## 7. Deployment 域

### 7.1 Docker

```text
功能：后端 / 前端镜像
状态：PARTIAL
代码位置：Dockerfile.backend、Dockerfile.frontend
当前实现：
  - backend：单阶段 python:3.12-slim，安装 requirements（含 torch/transformers），uvicorn 启动
  - frontend：两阶段 node:20-alpine → nginx:alpine
存在问题：
  1) [P0 安全-实测] 根目录与 backend/ **均无 .dockerignore**，而 Dockerfile.backend 是 COPY backend/ .
     → 本地构建会把 backend/.env（含真实 API Key）打进镜像；构建上下文约 2.8GB
  2) 无 HEALTHCHECK；容器以 root 运行；装 gcc 未清理
  3) torch 未使用 CPU-only 源；嵌入模型运行期下载且无 HF 缓存卷 → 冷启动慢 / 无离线能力
  4) 前端容器未挂 nginx.conf（无 SPA rewrite）→ 深链接刷新 404
改进建议：
  - 加 .dockerignore（.env、.venv、venv、node_modules、*.db、chroma_db、uploads、__pycache__）
  - 补 HEALTHCHECK；非 root 用户；模型缓存卷；前端挂 SPA rewrite 配置
优先级：P0（1）；P1（2、3、4）
```

### 7.2 Docker Compose

```text
功能：本地 / 生产编排
状态：COMPLETE
代码位置：docker-compose.yml、docker-compose.prod.yml
当前实现：
  - dev：postgres / redis / backend / frontend / nginx，healthcheck + condition: service_healthy
  - backend volumes：uploads_data、chroma_data、./backend/logs
  - prod：backend 改 expose，env_file 用 .env.production.local
存在问题：
  1) backend 在 dev 直接发布 8000（可绕过 nginx，绕过后 client_max_body_size 问题消失 → 环境差异）
  2) prod 的 443/certs 默认注释 → 默认明文 HTTP
  3) compose 中无 Prometheus / Grafana 服务（monitoring 只有配置文件）
改进建议：与 §7.5 Nginx、§5.6 Monitoring 一并处理
优先级：P2
```

### 7.3 Kubernetes

```text
功能：K8s 清单
状态：PARTIAL
代码位置：k8s/{backend-deployment,frontend-deployment,configmap,secret,hpa}.yaml
当前实现：Deployment×2 + Service×2 + Ingress + ConfigMap + Secret + HPA(v2, 2→10, CPU70%/MEM80%)
存在问题：
  1) [部署失败] Deployment 引用 PVC（chroma/uploads），但清单中**没有 PVC 定义** → Pod Pending
  2) [架构矛盾] replicas=2 + HPA 与本地 ChromaDB PersistentClient 互相矛盾（向量数据分叉）
  3) 每个副本启动都执行 init_db()/alembic upgrade head → 并发迁移竞态，应有独立 migration Job
  4) Ingress 缺 nginx.ingress.kubernetes.io/proxy-body-size: 50m
  5) 镜像标签与 compose（1.0.1）/CI（latest、sha）不一致，无 digest 绑定
改进建议：补 PVC；明确"本地向量库 → 单副本"的限制并写进文档；迁移改 Job；补 proxy-body-size
优先级：P1
```

### 7.4 Helm

```text
功能：Helm Chart
状态：SCAFFOLD
代码位置：helm/knowledge-chat/{Chart.yaml,values.yaml}、helm/knowledge-chat/templates/_helpers.tpl
存在问题：
  1) [实测] templates/ 下**只有 _helpers.tpl**，无任何资源模板 → `helm install` 创建 0 个资源
  2) README.md:326-331 的教学命令因此不可用（DOC_ONLY）
改进建议：二选一 —— 补齐 templates（deployment/service/ingress/configmap/secret/pvc），
  或在 README 明确标注 "Planned（当前仅有 values 骨架）"
优先级：P1
```

### 7.5 Nginx

```text
功能：反向代理
状态：PARTIAL
代码位置：nginx/nginx.conf、nginx/nginx.ssl.conf
当前实现：gzip、静态资源 30d 缓存、三条安全头、/api/ → backend:8000
存在问题：
  1) [P0 功能] 全仓库无 client_max_body_size → Nginx 默认 1m，
     而应用侧 MAX_FILE_SIZE=50MB（core/config.py:114）→ 经 Nginx 上传 >1MB 文件 413
  2) /api/ 无条件 `Connection: upgrade` 破坏 keepalive
  3) X-Forwarded-For 用 $proxy_add_x_forwarded_for（保留客户端伪造前置值）→ 限流可绕过
  4) /health 直接 return 200 "OK"，从不访问后端（探针无效）
  5) /ws/ 是无对应后端路由的死配置
改进建议：加 client_max_body_size 50m；X-Forwarded-For 用 $remote_addr；
  移除死配置；/health 改代理后端真实 health
优先级：P1（1、3）
```

### 7.6 CI/CD

```text
功能：持续集成 / 镜像构建
状态：COMPLETE（覆盖度 PARTIAL）
代码位置：.github/workflows/ci.yml、.github/workflows/docker-build.yml
当前实现：
  - ci.yml：起 postgres:16 + redis:7（healthcheck）→ pip install -r requirements.txt
    + python -m pytest tests/ -v → npm ci + npm run build
  - docker-build.yml：构建并推送 backend / frontend 镜像（latest + sha）
存在问题：
  1) [白起] 测试步骤强制 DATABASE_TYPE=sqlite / DATABASE_URL=sqlite+aiosqlite:///./test.db
     → 起的 PostgreSQL 与 Redis 完全没用上；缺 PostgreSQL matrix job
  2) 无 lint（PHASE6_FINAL_REPORT 自己承认 ruff 未安装）、无覆盖率门禁
  3) 无 .dockerignore → 镜像构建层没有任何体积 / 泄漏防护
  4) 镜像标签三处不一致（CI latest+sha / compose 1.0.1 / k8s latest），无 @sha256
改进建议：加 PostgreSQL job（可立刻暴露 api_keys 缺表类问题）；加 ruff + 覆盖率；
  统一镜像标签策略
优先级：P2
```

---

## 8. Testing 域

### 8.1 Unit Tests

```text
功能：单元测试
状态：PARTIAL
代码位置：backend/tests/（20 个文件）
当前实现（实测）：235 collected / 235 passed；覆盖 LLM Provider、Embedding Factory、BM25、
  Reranker 抽象、Cache、Worker、API Key、Audit Log、JWT 黑名单、限流、连接池、
  组织模型、向量生命周期、Chat 持久化、Security、LLM 配置、DB 迁移
存在问题：
  1) [有效性] 大量用例使用 AsyncMock(spec=AsyncSession) + patch 模型类
     → **没有一条 SQL 真正执行**；真实 DB 才暴露的问题（缺表、datetime 时区）无法被发现
  2) [弱断言] test_sprint32_production.py:106 `assert _metrics_available in [True, False]` 恒真；
     :144 只 `assert logger is not None`；多数"生产化"用例只断言文件路径存在
  3) [自指] test_db_migration.py 把 env.py 逻辑在测试里复写再断言自己
  4) [静默跳过] test_document_parser.py 的 PDF/DOCX 用例依赖未声明的 reportlab，
     遇 ImportError 直接 return（不是 pytest.skip）→ 用例永远"通过"但空跑
改进建议：关键路径改为"真实对象 + 真实内存 SQLite / 临时向量库"；
  消除恒真断言；依赖缺失一律 pytest.skip
优先级：P0-5（否则 Phase 1–3 的新功能无法被有效保护）
```

### 8.2 Integration Tests

```text
功能：集成测试
状态：PARTIAL
代码位置：backend/tests/test_sprint30_integration.py（组织 CRUD / 成员管理真实 SQLite 断言）
存在问题（实测）：
  1) `pytest tests/test_sprint30_integration.py --collect-only` → **no tests collected**
     原因：测试写成模块级 `async def run_all_tests()` + `if __name__ == "__main__"`，
     没有 test_* 函数；且仓库无 conftest.py / pytest.ini / pyproject.toml，未配置 asyncio_mode
  2) 结果：Organization 的真实 SQLite 集成断言**在 CI 里一次都没跑过**（CI 显示的绿是"0 用例"的绿）
改进建议：改写为 pytest 可收集的 test_* 函数；补 conftest.py（含内存 SQLite fixture）
优先级：P0-5
```

### 8.3 RAG Tests

```text
功能：RAG 链路测试（Query Rewrite / Retrieval / BM25 / Hybrid / Reranker / Abstention / Citation / Ingestion）
状态：MISSING
代码位置：无（检索相关测试仅 backend/tests/test_sprint31_ai_enhancement.py）
存在问题：
  1) 无 retrieval_pipeline 测试；无 citation 测试；无 abstention 测试；无 ingestion 全链路测试
  2) test_sprint31 的 TestHybridSearch 只测 BM25Retriever 类本身（未接入主链路）；
     TestReranker 只测"抽象类不能被实例化"
  3) test_sprint31 的 TestWorkflow / TestAgent / TestToolCalling / TestAIPipeline
     **在测试内部自定义了玩具类**（Tool、ToolRegistry、Workflow、Agent），
     与生产代码零关系 → 测试通过不代表任何功能存在
改进建议：Phase 1 每新增一个 RAG 组件（Rewrite / BM25 / Hybrid / Rerank / Filter /
  Abstention / Citation）同时补对应测试；把 test_sprint31 的玩具用例重写为对生产模块的
  真实测试或删除
优先级：P0-5
```

### 8.4 API Tests

```text
功能：HTTP 层测试
状态：MISSING
代码位置：无
存在问题：
  1) 全仓库无 TestClient / httpx 用法 → 没有任何路由级测试
  2) 因此 RBAC 500、IDOR、锁定登录 500、session 列表 500、Nginx 413 类问题无法被测试捕获
改进建议：引入 fastapi.testclient（或 httpx.ASGITransport）+ 内存 SQLite fixture，至少覆盖：
  登录、知识库 CRUD、上传、RAG 问答、流式控制帧、权限拒绝
优先级：P0-5
```

### 8.5 RAG Evaluation

```text
功能：离线评测体系
状态：MISSING
代码位置：无（无 evaluation/ 目录、无数据集、无指标实现、无评测脚本）
存在问题：
  1) 现有文档（docs/INTERVIEW_GUIDE.md §6.4）自己承认"未建评测集，给不出可信准确率"
  2) 无 Recall@K / MRR 实现；无 Faithfulness / Answer Relevancy / Context Relevancy
  3) 无法证明 Phase 1 的 Hybrid / Reranker 是否真的带来提升
改进建议：Phase 2 建立 evaluation/dataset（≥50 条，含 NO_ANSWER 类）+ 指标实现 + 报告，
  保留 Vector-only Baseline 做对比
优先级：P1（Phase 2 主体）
```

---

## 9. README 与代码的偏差清单（DOC_ONLY 汇总）

> 原则：`README = 实际代码 = 测试`。以下条目当前**不满足**该原则，必须在 Phase 5 修正或明确标注 `Planned`。

| # | README 位置与宣称 | 实际状态 | 标记 |
|---|---|---|---|
| 1 | `README.md:61`「Agents / Workflows / Tools：AI Agent 平台框架」 | 后端完全不存在（无 model / service / router） | DOC_ONLY |
| 2 | `README.md:21,63-67`「可观测性中心：系统监控、AI 指标、Token 分析、错误追踪」 | `/metrics` 未注册、埋点零调用、`llm_usages` 无写入端 → 4 个页面恒 0 | DOC_ONLY |
| 3 | `README.md:100,102`「Helm / Kubernetes 编排」「Prometheus + Grafana」 | Helm 无资源模板；Grafana 仅 `.gitkeep`；compose/k8s 无监控载体 | SCAFFOLD / DOC_ONLY |
| 4 | `README.md:47`「Knowledge ACL：知识库 4 级访问权限」 | `knowledge_acls` 为死表（无任何读取方），实际只有 user_id 私有权 | DOC_ONLY |
| 5 | `README.md:19,50-54`「安全中心 / RBAC」 | RBAC join 缺表（ADMIN 后台 500）、`user_roles` 无写入方；IDOR 未修 | PARTIAL（需在 README 降级描述） |
| 6 | `README.md:371-372`「`CACHE_BACKEND=redis` / `REDIS_*`」 | Redis 客户端 `protocol=1` 非法 → 恒连不上；`init_providers()` 不调用 → redis 永远不生效 | DOC_ONLY |
| 7 | `README.md:325-331` Helm 安装命令 | templates 为空 → 创建 0 资源 | DOC_ONLY |
| 8 | `README.md:333-334`「k8s/Helm 部署依赖 PostgreSQL 与 Redis 实例」 | K8s 清单缺 PVC，Pod 会 Pending | PARTIAL |
| 9 | `README.md:379-385`「后端测试 pytest / 前端构建验证」 | 235 passed 属实，但 §8 的有效性问题成立 | PARTIAL（需在 README 说明测试有效范围） |
| 10 | `README.md:81` 嵌入模型 `BAAI/bge-small-zh-v1.5` + `core/config.py:107` `EMBEDDING_DIM=768` | 该模型实际 512 维 → 自相矛盾 | 需修正 |
| 11 | `README.md:3,411` 版本 v1.0.1 / `VERSION` / `Chart.yaml` | `core/config.py:48` `APP_VERSION="1.0.0"`（并由 `/api/health` 报出）→ 版本漂移 | 需修正 |

---

## 10. 对已有文档的修正（避免继续引用过时结论）

审计复核发现 `docs/INTERVIEW_GUIDE.md`（上一轮审计）有**已过时条目**，后续阶段应以本报告为准：

| INTERVIEW_GUIDE 条目 | 本次复核结论 |
|---|---|
| §5.1「PDF 上传必然 FAILED（`doc.close()` 后访问 `doc[0]`）」 | **已修复**：`pdf_parser.py:46` 在 `close()` 前已收集 `page_texts`，close 之后只读 `page_texts[0]`（:61） |
| §5.9「Redis 客户端永远建不起来（`protocol=1`）」 | **仍成立**，且本次定位到确切异常：`ping() → ConnectionError: protocol must be either 2 or 3`（redis-py 8.0.1） |
| §5.2「`api_keys` 表在迁移库上不存在」 | **仍成立**（开发库实测 26 张表无 `api_keys`；迁移 `d5660fbbb75e` 仍为 `pass`） |
| §5.11「`test_sprint30_integration.py` 收集 0 用例」 | **仍成立**（实测 `no tests collected`） |
| §5.5「naive/aware datetime 导致 4 处 500」 | **仍成立**（`models/user.py` 等仍为 `Column(DateTime)`，无 timezone） |
| §5.4「IDOR：带 conversation_id 跳过 KB 校验」 | **仍成立**（`api/knowledge_query.py:131`） |
| §5.10「可观测性链路是断的」 | **仍成立**（metrics router 仍未注册、埋点仍零调用） |

> 结论：**INTERVIEW_GUIDE.md 仍是有效的架构与话术参考，但其"已知缺陷"章节需与本报告对齐**。
> 本报告不修改 INTERVIEW_GUIDE.md（Phase 0 只做审计），Phase 5 文档阶段统一处理。

---

## 11. Phase 1–5 的前置条件与设计风险

在 Phase 1 开工前必须对齐的设计决策（这些是从当前代码结构推导出的、会直接影响落地方式的约束）：

### 11.1 BM25 的语料从哪里来？（Phase 1 最大设计缺口）

```text
现状：services/retrieval/bm25.py 的 BM25Retriever 是**内存态**：
      fit(documents) 一次性喂语料，search() 只遍历 self._documents
问题：文档真实存放在 ChromaDB（本地持久化），进程可重启、KB 可增删文档
      → 若每次查询都从 Chroma 拉全量文档重建索引，chunk 量上去后延迟会失控
可选方案：
  (a) 持久化稀疏索引（SQLite FTS5 / 自建倒排文件）+ 文档变更时增量更新   ← 推荐
  (b) 进程内缓存索引 + 文档增删时失效重建
  (c) 换支持混合检索的向量库 —— **违反"不更换 Vector DB"约束，排除**
影响：方案 (a) 需要新增存储与同步逻辑（是否加表？是否复用 Chroma 的 documents 字段？）
```

### 11.2 中文分词是新依赖决策点

```text
现状：bm25.py:25 用 str.lower().split()，对中文等于**完全不分词**（整段成为一个 term）
选项：字符 bi-gram（零新增依赖、索引膨胀）/ jieba（效果好、新增依赖）
建议：先做 bi-gram 保证"零依赖 + 可测"，把 jieba 作为可选增强并写清权衡
```

### 11.3 `BaseRetriever.retrieve` 签名必须演进

```text
现状：retrieve(embedding, knowledge_base_id, top_k)（retrieval/base.py:53）——不含原始 query
需要：BM25 / Hybrid 需要 query 文本
建议：新增关键字参数 query: str | None = None，保留原位置参数与默认值，避免破坏现有调用与测试
```

### 11.4 Reranker 的形态与依赖成本

```text
现状：Reranker 只有抽象类，无任何实现
约束：cross-encoder（如 bge-reranker-v2-m3）需 transformers + torch 额外加载模型
      → 镜像更大、首次冷启动更慢
建议：定义具体实现 + **失败/超时自动 fallback 到融合排序**（满足计划要求）；
      默认可关闭（配置驱动），并在容器中预留模型缓存卷
```

### 11.5 评测集需要真实文档与 API Key

```text
现状：backend/.env 有真实 LLM key（本报告不打印），CI 无 key
影响：检索指标（Recall@K / MRR）可离线复现（本地嵌入模型）；
      生成指标（Faithfulness 等）无法在 CI 运行
建议：检索指标走离线可复现路径；生成指标标记"需 API Key 手动运行"，
      并在 docs/RAG_EVALUATION.md 中如实说明运行前提（禁止伪造数据）
```

### 11.6 阈值 / 权重的配置落点

```text
现状：min_score 在 RetrievalPipeline 类属性（:44）、retrieval_top_k 在 DB KnowledgeConfig、
      CHUNK_* 在 settings —— 三处分散
需要：Hybrid 权重、Reranker top_k、Context 阈值、Abstention 阈值全部可配
建议：统一为"settings 默认 ← KnowledgeConfig 覆盖"，扩展现有 KnowledgeRuntimeConfig，
      而不是新增散落的常量
```

### 11.7 Async Ingestion 的 Worker 必须重写执行模型

```text
现状：LocalWorker 用 asyncio.ensure_future（绑定请求 loop）+ 内存 _tasks dict
不满足：上传后请求立即返回、任务独立存活、状态可跨进程查询
建议：独立线程/事件循环执行 + 任务状态落 DB（不复用内存 dict）
```

### 11.8 必须先止血的 P0 阻塞项

Phase 1/2/3 的成果要"可验证"，依赖以下 P0 项先修（均为小改动、高收益，且不违反计划的禁止事项）：

```text
P0-1  core/redis.py protocol=1 → 2                      限流恢复（当前等同不存在）
P0-2  Embedding 兜底改显式失败 + EMBEDDING_DIM 修正 512   防脏向量，保 Phase 2 评测可信
P0-3  Citation 的 citations 接入 SSE + 补 page/section    Phase 1 §5.5 前置
P0-4  DocumentStatus 加 PENDING + Worker 执行模型         Phase 3 前置
P0-5  补 conftest.py（内存 SQLite）+ 修 test_sprint30     Phase 2 前置（否则评测无测试保护）
附带（同批止血，成本极低）：
  - IDOR：从 conversation_id 反查并校验 KB 归属（§6.2）
  - SECRET_KEY 默认值 fail-fast（§6.1）
  - 加 .dockerignore（§7.1）
  - nginx client_max_body_size 50m + X-Forwarded-For $remote_addr（§7.5）
```

> **待用户确认**（本报告不擅自执行）：
> 1) 是否将 P0-1 / P0-2 / P0-5 纳入 Phase 1 一并完成？（缺此三项，Hybrid/Reranker 的收益无法被评测证明、也无法被测试保护）
> 2) BM25 语料方案选 (a) 持久化倒排 还是 (b) 进程内索引 + 失效？
> 3) 中文分词选 零依赖 bi-gram 还是 jieba？

---

## 12. 优先级汇总

| 优先级 | 条目 |
|---|---|
| **P0（必须先处理）** | Redis `protocol=1`；Embedding 随机兜底 + DIM 错配；Citation/page 追溯；Async Ingestion 状态机与 Worker 执行模型；测试基础设施（conftest + test_sprint30 收集 + 弱断言清理）；IDOR；SECRET_KEY 默认值；`.dockerignore` |
| **P1（Phase 1–3 主体）** | Query Rewrite；Hybrid Retrieval（含 BM25 语料与分词决策）；Reranker；Context Score Threshold；Abstention；Citation 一致性；评测集与指标；Retry；Idempotency；请求级观测（request_id + 分段耗时）；`/metrics` 注册 + 埋点接入；`usage_service.record()` 接入；SSE 协议显式类型；多轮上下文回读；Nginx / K8s / Helm 修正 |
| **P2（打磨）** | Chunking token 化与 heading-aware；Parser 的 page/section 结构；LLM Provider 去重；Prompt 增强；限流合并；日志脱敏；镜像瘦身；CI 加 lint / 覆盖率 / PostgreSQL job；版本号与镜像标签统一 |
| **P3（Phase 4）** | Agent / Workflow / Tools（仅做 1 个真实场景）；前端空壳页面与死代码清理 |

---

## 13. Phase 0 声明

```text
审计范围：全仓库只读审查 + 测试实测 + 开发库只读查询 + 缺陷复现
是否修改业务代码：否
是否删除文件/数据：否
是否创建文件：仅本报告 docs/KNOWLEDGE_CHAT_REALITY_AUDIT.md
是否进入 Phase 1：否 —— 等待本报告审核确认后开始
```

**下一步（Phase 1，待审核后启动）**：

```text
Phase 1 建议顺序（与计划 §20 一致，每步独立 commit + 独立测试）：
  1. feat(rag): add query rewrite
  2. feat(rag): add hybrid retrieval（含 BM25 语料方案落地）
  3. feat(rag): add reranker
  4. feat(rag): add context filtering
  5. feat(rag): improve citation
  6. feat(rag): add abstention
每个子步骤同时补：
  - Unit Test（正常 / 空输入 / 依赖失败 fallback）
  - 与 P0-2 / P0-5 相关的可复现性保障
```

---

## 14. 整改进度（2026-09-30）

本节记录 §1–§12 各项结论的**当前**状态与对应 commit。审计正文保持为审计当日的快照
（不做追溯修改，避免掩盖当时的实测证据）；判断"现在能不能用"请以本表为准。

| 审计条目 | 问题 | 状态 | commit |
|---|---|---|---|
| §6.2 | 知识库越权读（IDOR）：仅"无会话"分支校验归属 | ✅ 已修复（两条分支统一校验知识库 / 会话 / 一致性） | `4ac39e8` |
| §6.1 | 占位 `SECRET_KEY` 可上线、`/docs` 生产暴露 | ✅ 已修复（fail-fast + 按环境关闭文档） | `3bb33f4` |
| §6.3 | RBAC 联表导致管理后台全量 500 | ✅ 已修复（联表 + 遗留角色映射 + ROOT 收敛） | `dd815fa` |
| §6.1 / §5.3 | token 不校验用户状态、API Key 通道不可用、naive/aware UTC | ✅ 已修复 | `d8ca420` |
| §3.5 / §5.5 | 500 拼接 `str(e)` 泄漏内部信息、错误契约不统一 | ✅ 已修复（固定文案 + `code` + `request_id`，异常只进日志） | `0aa43bb` |
| §5.3 | `api_keys` 迁移为空桩（表根本不存在） | ✅ 已修复（迁移建表 + 不再手工维护模型 import） | `4c24dc5` |
| §4 | Agent / Workflow / Tools 后端缺失、前端假数据冒充功能 | 🟡 部分修复：工具层真实落地（`kb_search` / `calculator` + `/api/tools`）；Agent / Workflow 明确标注 Planned | `474ebfa` |
| §12 P3 / §4（前端侧） | `AgentStudioPage` / `WorkflowStudioPage` 会真实请求不存在的 `/agents`、`/workflows`，失败被 `catch` 吞成空数组（页面看似可用、实际永远为空） | ✅ 已清理：空壳编排器 + 假客户端 + 死 store 整体删除，旧 URL 改为 redirect，测试钉住"禁止复活" | `fcacc25` |
| §7.1 / §7.2 | 缺 `.dockerignore` / 健康检查 / 前端 SPA rewrite | ✅ 已修复 | `80f36ba` |
| §7.3 / §7.5 | K8s 缺 PVC、多副本与 SQLite/向量库冲突；Nginx `X-Forwarded-For` 与上传体积 | ✅ 已修复 | `df585ba` |
| §7.4 / §5.6 | Helm 空壳（0 资源）、Grafana 面板缺失 | 🟡 仅文档标注 Planned（产物仍未落地） | `65920af` |
| §8.5 | 评测产物归档口径（smoke 产物混入） | ✅ 已修复 | `ccb1c86` |
| §3.2 等前端契约 | 前端未适配 Phase 3 后端契约 | ✅ 已修复 | `760d383` |

测试基线：审计当日 **235 passed** → 现在 **630 passed / 0 failed**；`backend/conftest.py`
提供真实 SQLite（schema 由模型元数据创建），`tests/test_sprint31_ai_enhancement.py`
中与生产无关的玩具类已删除（改为断言"未实现"这一事实）。

说明：本表只覆盖本轮整改板（Phase 1–3 收尾）的 commit。审计中其余**工程类**条目已由
Phase 1–3 的功能提交覆盖，例如统一重试 `16d9169`、上传幂等 `5f58d65`、Redis protocol `f67474b`、
异步入库 `9b95218`、指标与埋点 `4572adf`；请以代码与 §1 状态总览为准，不要按审计当日的旧结论判断。
仍未落地的**产物**：§7.4 Helm 资源模板、§5.6 Grafana 面板（两者已在 README 标注 Planned）。
前端空壳页面与死代码（§12 P3 的前端部分）已在 `fcacc25` 清理完毕；Agent / Workflow 若继续推进，
按 §4 的建议只做一个真实场景（KB 检索 + Calculator），并同步 README / 前端标注，不要重新引入空壳页面。

