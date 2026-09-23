# Agens 模型升级报告：agnes-2.5-flash

| 项目 | 内容 |
|------|------|
| 变更日期 | 2026-09-22 |
| 变更目标 | 将项目默认 LLM 从 `agnes-2.0-flash` 升级为 `agnes-2.5-flash`（Agens Provider） |
| 影响范围 | 后端配置与 Provider、启动日志、前端展示文案、Docker/K8s/Helm 模板、文档、测试 |
| 结论 | 已完成并验证通过：后端启动日志显示 `agens / agnes-2.5-flash`，真实 Agnes API 调用（非流式 + 流式 + ChatService 链路）均正常返回，后端全量测试 209 passed |

---

## 1. 背景与目标

项目原有 `.env` 已启用 Agens Provider（`LLM_PROVIDER=agens`），但模型名停留在 `agnes-2.0-flash`。
本次需要：

1. 将实际使用的模型改为 **`agnes-2.5-flash`**，并配置给定 API Key；
2. 项目内所有引用旧模型名的地方（前端展示、示例、部署模板、文档）保持一致；
3. 增加可验证性（启动日志、配置自检、单元测试）；
4. 输出本报告。

## 2. 变更清单

### 2.1 运行时配置（生效文件）

| 文件 | 变更前 | 变更后 |
|------|--------|--------|
| `.env`（根目录，Docker Compose 使用） | `LLM_MODEL=agnes-2.0-flash` | `LLM_MODEL=agnes-2.5-flash`（并补充可选模型注释） |
| `backend/.env`（本地后端启动使用） | `LLM_MODEL=agnes-2.0-flash` | `LLM_MODEL=agnes-2.5-flash` |
| `.env.production.local`（生产本地覆盖文件） | `LLM_PROVIDER=deepseek` / `AGENS_API_KEY=` 空值 | `LLM_PROVIDER=agens`、`LLM_MODEL=agnes-2.5-flash`、填入 AGENS_API_KEY |

两个 `.env` 中的 `AGENS_API_KEY` 与 `AGENS_API_BASE=https://apihub.agnes-ai.com/v1` 保持不变（与原配置一致且验证可用）。

### 2.2 配置模板

| 文件 | 变更 |
|------|------|
| `.env.example` / `backend/.env.example` | 模型注释由 “deepseek-chat 或 agnes-2.0-flash” 改为按 Provider 分类的可选模型清单（Agens 首选 `agnes-2.5-flash`） |
| `.env.production` | 生产模板补充模型与 Provider 匹配说明；Agens Key 保持占位符（真实 Key 只写 `.env.production.local`） |
| `docker-compose.yml` | 补充注释：推荐 `LLM_PROVIDER=agens` + `LLM_MODEL=agnes-2.5-flash`（变量仍从 `.env` 读取） |
| `k8s/configmap.yaml` | `LLM_PROVIDER: agens`、新增 `LLM_MODEL: agnes-2.5-flash`、`AGENS_API_BASE` |
| `k8s/secret.yaml` | 新增 `AGENS_API_KEY: "your-agens-api-key"` 占位（真实值由部署方注入） |
| `helm/knowledge-chat/values.yaml` | `config.llmProvider: agens`、新增 `llmModel` / `agensApiBase`，`secrets.agensApiKey` |

### 2.3 后端代码

| 文件 | 变更 |
|------|------|
| `app/core/config.py` | ① `AGENS_API_BASE` 默认值补全为 `https://apihub.agnes-ai.com/v1`；② 新增 `LLM_PROVIDERS` / `PROVIDER_MODEL_PREFIXES` / `KNOWN_MODELS` 元数据；③ 新增 `Settings.check_llm_config()` 配置自检方法 |
| `app/main.py` | 启动日志新增当前模型（`🔗 LLM Provider: agens \| 🤖 LLM 模型: agnes-2.5-flash`），并对 `check_llm_config()` 返回的问题逐条输出 `⚠️ LLM 配置检查` 告警 |
| `app/services/llm/agens_provider.py` | 适配推理型模型：忽略 reasoning 增量、去除正文首个 chunk 的前导换行（流式 `_stream_response`），非流式 `chat()` 同样裁剪前导空白 |
| `app/core/logging.py` | 控制台 sink 编码安全化：Windows GBK 控制台无法编码 emoji 时会抛 `UnicodeEncodeError` 并刷屏 `--- Logging error ---`；现在自动切换 UTF-8（`errors="replace"`），文件 sink 显式 `encoding="utf-8"` |

`check_llm_config()` 校验项：

- `LLM_PROVIDER` 是否在受支持列表（`deepseek` / `agens`）；
- `LLM_MODEL` 是否为空、模型名前缀是否与 Provider 匹配（agens → `agnes*`）；
- 模型名是否在 `KNOWN_MODELS` 列表内（不在则提示确认 Provider 侧是否提供）；
- 对应 Provider 的 API Key / Base URL 是否配置。

### 2.4 前端

| 文件 | 变更 |
|------|------|
| `src/pages/ai/AgentManagementPage.tsx` | 占位 Agent 模型 `agnes-2.0-flash` → `agnes-2.5-flash` |
| `src/pages/platform/models/ModelCenterPage.tsx` | 新增模型的默认 Provider `deepseek` → `agens`；占位提示改为 `e.g. agens` / `e.g. agnes-2.5-flash` |
| `src/pages/admin/SystemConfig.tsx` | 配置兜底展示值改为 `agens` / `agnes-2.5-flash` |
| `src/api/client.ts` | 401/402 错误提示由仅提 DeepSeek 改为 Provider 中立（`AGENS_API_KEY` / `DEEPSEEK_API_KEY`） |

### 2.5 文档与测试

| 文件 | 变更 |
|------|------|
| `README.md` | 环境变量表补充 Agens 模型说明与「切换 LLM 模型」提示；Docker/K8s/Helm 示例与占位值清单更新 |
| `docs/provider_system.md` | LLM Provider 表补充常用模型、`.env` 示例、配置自检与推理型模型说明 |
| `CHANGELOG.md` | 新增本次变更条目 |
| `backend/tests/test_llm_config.py` | **新增 19 个用例**：配置自检（9）、`.env` 回归保护（1）、Provider 装配（4）、输出规范化（5） |

---

## 3. 验证证据

### 3.1 Agnes 服务端模型探测（真实请求）

```
GET https://apihub.agnes-ai.com/v1/models
→ agnes-2.0-flash, agnes-2.5-flash, agnes-2.5-pro, agnes-2.5-pro-alpha,
  agnes-2.5-pro-beta, agnes-3.0-flash, agnes-image-*, agnes-video-*
```

确认 `agnes-2.5-flash` 为该 API Key 可用的文本模型。

### 3.2 项目链路真实调用

`app.services.chat_service.ChatService`（即 `/api/chat/chat`、`/api/chat/stream` 内部使用的服务）：

```
provider=AgensProvider model=agnes-2.5-flash
configured: agens / agnes-2.5-flash
---- ChatService.chat() ----
'我是 Agnes-2.5-Flash，由 Sapiens AI 开发的语言模型。'
---- ChatService.stream_chat() ----
chunks=48
'1. **提升信息检索效率**：…  2. **保证回答一致性**：…'
```

同时验证了 `LLMProviderFactory.create(settings)` → `provider._model == "agnes-2.5-flash"`，
且返回内容已无前导空行（`agnes-2.5-flash` 会先输出 `reasoning_content` 再输出正文）。

### 3.3 后端启动日志（uvicorn，端口 8112）

```
✅ 智能知识库问答系统 启动完成
📡 API 文档: http://localhost:8000/docs
🔗 LLM Provider: agens | 🤖 LLM 模型: agnes-2.5-flash
🔗 Agens API: https://apihub.agnes-ai.com/v1
🗄️  数据库: sqlite+aiosqlite:///./knowledge.db
📦 向量存储: chroma
🔤 嵌入模型: BAAI/bge-small-zh-v1.5
```

`GET /api/health` → `200 {"status":"healthy", ..., "llm_configured": true}`；启动过程无 `Logging error` 刷屏。

### 3.4 自动化测试

```
cd backend && python -m pytest tests/test_llm_config.py -v
→ 19 passed

cd backend && python -m pytest -q
→ 209 passed, 39 warnings
```

`test_llm_config.py` 关键断言：

- `KNOWN_MODELS["agens"]` 含 `agnes-2.5-flash`，且 `PROVIDER_MODEL_PREFIXES["agens"] == "agnes"`；
- `LLM_PROVIDER=agens + agnes-2.5-flash + API Key` → `check_llm_config() == []`；
- `agens` 搭配 `deepseek-chat` / 未知 `agnes-9.9-turbo` / 空 Key / 空 Base / 不支持的 Provider → 均能报出对应问题；
- `backend/.env` 若启用 agens，则其 `LLM_MODEL` 必须是合法 agnes 模型且 Key/Base 非空（回归保护，`.env` 缺失时自动 skip）；
- 流式首个正文 chunk 的前导换行被裁剪、后续换行保留、空 `choices` 与 `reasoning_content` 增量被跳过；
- 非流式：前导换行裁剪、`content=None` 返回 `""`。

---

## 4. 使用方式与回滚

### 使用

```bash
# 本地开发（backend 目录下启动）
cd backend && uvicorn app.main:app --reload --port 8000
```

```bash
# Docker Compose（根目录 .env 已配置好 agens / agnes-2.5-flash）
docker compose up -d --build
```

切换模型只需改环境变量，无需改代码：

```bash
LLM_PROVIDER=agens
LLM_MODEL=agnes-2.5-flash      # 可选 agnes-2.5-pro / agnes-3.0-flash / agnes-2.0-flash
AGENS_API_KEY=sk-xxx
AGENS_API_BASE=https://apihub.agnes-ai.com/v1
```

### 回滚

- 回退到旧版 Agens 模型：`.env` 中 `LLM_MODEL=agnes-2.0-flash`（`AgensProvider` 兼容）；
- 回退到 DeepSeek：`LLM_PROVIDER=deepseek` + `LLM_MODEL=deepseek-chat` + `DEEPSEEK_API_KEY`；
- 代码层无破坏性改动：`Settings.check_llm_config()` 为新增方法，前导空白裁剪与日志编码处理均为向后兼容行为。

---

## 5. 已知限制与后续建议

1. **推理 token 占用 `max_tokens`**：`agnes-2.5-flash` 为推理型模型，`reasoning_tokens` 计入 `completion_tokens`。
   当前 `ChatService` 使用 `max_tokens=2000`，实测短问答推理约 20~60 token，长上下文场景若出现回答被截断，
   建议将该值提升到 3000~4000（`app/services/chat_service.py` 三处 LLM 调用）。
2. **可选的 reasoning 参数**：Agens 会默认返回推理过程，本次未启用任何“关闭思考”参数（未在官方文档确认参数名，避免误传导致 400）。
   如后续需要降低延迟，可在 `AgensProvider.chat(**kwargs)` 传入并验证。
3. **嵌入模型未就绪**：本次验证环境无法访问 `hf-mirror.com`，`BAAI/bge-small-zh-v1.5` 未缓存，
   启动日志出现 `⚠️ Embedding service initialization issue`，`/api/health` 返回 `embedding_model: false`。
   这不影响通用聊天与本次 LLM 切换，但 **知识库 RAG 检索需要先让嵌入模型可用**（联网下载一次或离线放置模型文件）。
4. **密钥安全**：`AGENS_API_KEY` 以明文存放在本地 `.env`（已被 `.gitignore` 忽略）与 `.env.production.local`（同样忽略）。
   `.env.production` 模板中只保留占位符，请不要把真实 Key 写入受版本控制的文件；
   若 Key 曾出现在提交历史或聊天记录中，建议在 Agens 控制台**轮换该 Key**。
5. **k8s/Helm 仅为模板**：`helm/knowledge-chat/templates/` 下只有 `_helpers.tpl`，没有 Deployment 模板，
   Helm values 仅作参数约定；k8s 清单已可直接随 ConfigMap/Secret 注入 agens 配置（Secret 中需填入真实 Key）。

