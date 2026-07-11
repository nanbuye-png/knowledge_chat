# 🧠 智能知识库问答系统

一个企业级知识库问答系统，支持文档上传/删除、基于文档的精准问答（RAG）、以及通用 AI 闲聊对话。

## ✨ 功能特性

### 📚 文档管理
- 支持 PDF、Word（.docx）、Markdown、TXT 格式上传
- 自动解析、文本切块、向量化存储
- 文档列表展示（文件名、大小、状态、上传时间）
- 文档删除（同步清理向量数据）
- 实时处理状态反馈

### 🎯 知识库问答（RAG）
- 基于上传文档的精准问答
- 自动标注引用来源（文档名 + 段落）
- 无相关资料时友好提示
- 流式输出（SSE），打字机效果

### 💬 AI 闲聊
- 调用 DeepSeek API 进行通用对话
- 多轮对话上下文记忆
- 流式输出，实时显示

### 🎨 前端体验
- 深色/亮色主题一键切换
- 平滑动画（Framer Motion）
- Markdown + 代码高亮渲染
- 响应式设计（桌面 + 移动端）
- 毛玻璃导航栏效果
- 对话历史持久化（刷新不丢失）

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Vite + TypeScript + Tailwind CSS + Framer Motion |
| 后端 | FastAPI + Python 3.12 + SQLAlchemy (async) |
| 向量库 | ChromaDB（嵌入式，无需独立部署） |
| 嵌入模型 | BAAI/bge-small-zh-v1.5（本地运行） |
| LLM | DeepSeek API / Agens API（多 Provider 支持） |

## 🚀 快速开始

### 前置要求

- Python 3.12+
- Node.js 18+
- DeepSeek API Key

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd knowledge_chat
```

### 2. 后端配置与启动

```bash
cd backend

# 创建并激活虚拟环境
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp ".env copy.example" .env
# 编辑 .env 填入 API Key

# 启动后端服务
uvicorn app.main:app --reload --port 8000
```

首次启动会自动下载嵌入模型（约 500MB），请耐心等待。

### 3. 前端配置与启动

```bash
cd frontend
npm install
npm run dev
```

### 4. 访问系统

- **前端界面**：http://localhost:5173
- **API 文档**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/api/health

## 📡 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/documents/upload` | 上传文档 |
| GET | `/api/documents/` | 获取文档列表 |
| DELETE | `/api/documents/{id}` | 删除文档 |
| GET | `/api/documents/{id}/status` | 获取文档状态 |
| POST | `/api/chat/query` | 知识库问答 |
| POST | `/api/chat/chat` | 闲聊模式 |
| POST | `/api/chat/stream` | 流式闲聊（SSE） |
| POST | `/api/chat/stream/query` | 流式知识库问答（SSE） |
| GET | `/api/chat/mode` | 获取当前模式 |
| PUT | `/api/chat/mode` | 切换模式 |
| GET | `/api/llm-models` | 获取 LLM 模型列表 |
| POST | `/api/llm-models` | 创建 LLM 模型配置 |
| GET | `/api/llm-models/{id}` | 获取单个模型配置 |
| PUT | `/api/llm-models/{id}` | 更新模型配置 |
| DELETE | `/api/llm-models/{id}` | 删除模型配置 |
| GET | `/api/prompt-templates` | 获取 Prompt 模板列表 |
| POST | `/api/prompt-templates` | 创建 Prompt 模板 |
| GET | `/api/prompt-templates/{id}` | 获取单个模板 |
| PUT | `/api/prompt-templates/{id}` | 更新模板 |
| DELETE | `/api/prompt-templates/{id}` | 删除模板 |
| GET | `/api/prompt-templates/{id}/versions` | 获取模板版本历史 |
| POST | `/api/prompt-templates/{id}/rollback/{v}` | 回滚模板到指定版本 |

## 📁 项目结构

```
knowledge_chat/
├── backend/
│   ├── app/
│   │   ├── api/           # API 路由
│   │   ├── auth/          # 认证相关
│   │   ├── core/          # 配置、日志、异常
│   │   ├── models/        # 数据库模型
│   │   ├── prompts/       # Prompt Provider（模板管理 & 动态加载）
│   │   ├── providers/     # LLM Provider（DeepSeek / Agens）
│   │   ├── schemas/       # Pydantic 校验
│   │   ├── services/      # 业务逻辑
│   │   ├── storage/       # 存储层
│   │   ├── utils/         # 工具函数
│   │   └── main.py        # 应用入口
│   ├── requirements.txt
│   └── tests/             # 测试
├── frontend/
│   ├── src/
│   │   ├── api/           # API 调用
│   │   ├── components/    # UI 组件
│   │   ├── contexts/      # 状态管理
│   │   ├── pages/         # 页面
│   │   ├── store/         # 状态存储
│   │   ├── types/         # TypeScript 类型
│   │   └── App.tsx        # 主应用
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 🤖 Multi LLM Provider Support

系统支持多 LLM Provider，目前内置以下提供商：

| Provider | 状态 | 说明 |
|----------|------|------|
| **DeepSeek** | ✅ 已支持 | OpenAI 兼容 API，支持 Stream + JSON |
| **Agens** | ✅ 已支持 | 假定 OpenAI 兼容 API，支持 Stream |

### 切换 Provider

只需修改 `.env` 文件，**无需修改任何代码**：

```bash
# 使用 DeepSeek
LLM_PROVIDER=deepseek

# 或使用 Agens
LLM_PROVIDER=agens
```

### 未来可扩展

架构已预留接口，可轻松接入更多 Provider：

- OpenAI
- Gemini
- Qwen

新增 Provider 只需编写一个 `BaseLLMProvider` 子类并在工厂中注册即可接入，无需修改 ChatService、API 或前端代码。

## ⚙️ 配置说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `LLM_PROVIDER` | LLM 提供商（deepseek / agens） | deepseek |
| `LLM_MODEL` | 模型名称 | deepseek-chat |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |
| `DEEPSEEK_API_BASE` | DeepSeek API 地址 | https://api.deepseek.com |
| `AGENS_API_KEY` | Agens API Key | - |
| `AGENS_API_BASE` | Agens API 地址 | - |
| `EMBEDDING_MODEL` | 嵌入模型 | BAAI/bge-small-zh-v1.5 |
| `LOG_LEVEL` | 日志级别 | INFO |
| `CHUNK_SIZE` | 文档切块大小 | 500 |
| `CHUNK_OVERLAP` | 切块重叠 | 100 |
| `MAX_FILE_SIZE` | 最大文件大小 | 50MB |

## 🔧 变更日志

### Sprint 15 — Prompt 模板管理 & 动态加载 (2026-07-11)

- **PromptTemplate 数据模型**：新增 `prompt_templates` 表，支持 name / prompt_type / content / version / enabled 字段
- **PromptTemplate CRUD API**：完整的 RESTful 管理接口（创建、查询、更新、删除）
- **Prompt 版本管理**：每次修改 content 自动创建不可变版本快照（`prompt_template_versions`），支持版本历史查询与回滚
- **DatabasePromptProvider**：从数据库动态加载 Prompt 模板，ChromeDB 优先，DefaultPromptProvider 兜底
- **Prompt Factory 扩展**：`get_prompt_provider("database", session=db)` 新增数据库 Provider 注册
- **ChatService 动态接入**：`chat()` / `query_knowledge()` / SSE 全链路支持运行时切换 Prompt Provider

### Sprint 13.3 — Architecture Polish & Documentation (2026-07-11)

- **Provider 文档完善**：所有 Provider 模块补充统一风格 Docstring
- **Factory 常量**：新增 `SUPPORTED_PROVIDERS` 注册表，新 Provider 只需在此注入
- **代码整理**：移除未使用 import，统一类型注解
- **README 更新**：新增 Multi LLM Provider Support 章节

### Sprint 11 — 生产环境加固 (2026-07-10)

- **SQLite 数据库路径固定**：`DATABASE_URL` 中的相对路径基于 `backend/` 目录自动转换为绝对路径，确保无论启动目录在哪里都使用同一个 `knowledge.db`
- **ChromaDB 持久化路径固定**：`CHROMA_PERSIST_DIR` 和 `UPLOAD_DIR` 同样基于项目 `backend/` 目录固定为绝对路径，避免向量数据丢失
- **SSE 流式聊天 JWT Token 修复**：前端 `createStreamChat()` / `createStreamKnowledgeQuery()` 的 `fetch()` 请求现在携带 `Authorization: Bearer` 头，解决流式接口 401 问题

---

## 📋 验收清单

- [x] 上传 PDF/Word/Markdown/TXT，侧边栏显示文档列表
- [x] 删除文档，侧边栏和向量数据同步移除
- [x] 知识库模式：提问返回回答 + 引用来源
- [x] 知识库模式：无相关资料时返回"抱歉"
- [x] 闲聊模式：调用 DeepSeek API 返回通用回答
- [x] 模式切换流畅，界面有清晰状态提示
- [x] 界面美观、动效流畅、支持深色/亮色主题
- [x] API 有完善的错误处理和日志
- [x] 虚拟环境本地一键启动成功

## 📄 许可证

MIT