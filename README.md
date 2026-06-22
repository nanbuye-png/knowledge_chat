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
| 后端 | FastAPI + Python 3.11 + SQLAlchemy (async) |
| 向量库 | ChromaDB（嵌入式，无需独立部署） |
| 嵌入模型 | BAAI/bge-small-zh-v1.5（本地运行） |
| LLM | DeepSeek API |
| 部署 | Docker Compose |

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- DeepSeek API Key

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd knowledge_chat
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 DeepSeek API Key：

```env
DEEPSEEK_API_KEY=sk-your-api-key-here
```

### 3. 启动服务

```bash
docker-compose up -d
```

首次启动会自动下载嵌入模型（约 500MB），请耐心等待。

### 4. 访问系统

- **前端界面**：http://localhost
- **API 文档**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/api/health

## 🛠️ 本地开发

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 API Key
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器运行在 http://localhost:5173，自动代理 API 请求到后端。

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

## 📁 项目结构

```
knowledge_chat/
├── backend/
│   ├── app/
│   │   ├── api/           # API 路由
│   │   ├── core/          # 配置、日志
│   │   ├── models/        # 数据库模型
│   │   ├── schemas/       # Pydantic 校验
│   │   ├── services/      # 业务逻辑
│   │   ├── storage/       # 存储层
│   │   ├── utils/         # 工具函数
│   │   └── main.py        # 应用入口
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/           # API 调用
│   │   ├── components/    # UI 组件
│   │   ├── contexts/      # 状态管理
│   │   ├── types/         # TypeScript 类型
│   │   └── App.tsx        # 主应用
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## ⚙️ 配置说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |
| `DEEPSEEK_API_BASE` | API 地址 | https://api.deepseek.com |
| `LLM_MODEL` | 模型名称 | deepseek-chat |
| `EMBEDDING_MODEL` | 嵌入模型 | BAAI/bge-small-zh-v1.5 |
| `LOG_LEVEL` | 日志级别 | INFO |
| `CHUNK_SIZE` | 文档切块大小 | 500 |
| `CHUNK_OVERLAP` | 切块重叠 | 100 |
| `MAX_FILE_SIZE` | 最大文件大小 | 50MB |

## 📋 验收清单

- [x] 上传 PDF/Word/Markdown/TXT，侧边栏显示文档列表
- [x] 删除文档，侧边栏和向量数据同步移除
- [x] 知识库模式：提问返回回答 + 引用来源
- [x] 知识库模式：无相关资料时返回"抱歉"
- [x] 闲聊模式：调用 DeepSeek API 返回通用回答
- [x] 模式切换流畅，界面有清晰状态提示
- [x] 界面美观、动效流畅、支持深色/亮色主题
- [x] API 有完善的错误处理和日志
- [x] Docker Compose 一键启动成功

## 📄 许可证

MIT