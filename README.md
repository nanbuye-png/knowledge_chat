# knowledge_chat · 企业级 AI 知识库平台

> **Enterprise AI Knowledge Platform** — v1.0.1

基于 FastAPI + React 的 AI 知识库平台，支持企业知识管理、RAG 增强问答、多模型 Provider、组织管理与安全中心。

---

## 🚀 产品概述

knowledge_chat v1.0.1 是一套面向企业的 AI 知识库平台，从最初的 RAG 问答工具，演进为具备 **企业管理后台、组织管理、安全中心、AI 能力中心、可观测性中心** 的完整企业 AI 平台。

| 模块 | 说明 |
|------|------|
| 💬 **AI Chat** | 多轮对话、流式输出、知识库问答 + 普通闲聊双模式 |
| 📚 **知识库** | 文档上传( PDF/DOCX/MD/TXT )、自动解析、Chunk 切分、向量化存储 |
| 🔍 **RAG Pipeline** | 文档 → 解析 → 切分 → 向量化 → 检索 → 引用标注 → 生成 |
| 🏢 **企业管理** | Organization、Members、Departments、ACL、Quota |
| 🔐 **安全中心** | RBAC 权限、审计日志、API Key、安全仪表盘 |
| 🤖 **AI 中心** | 多 Provider 管理、模型注册、Prompt 工程、配置管理 |
| 📊 **可观测性** | 系统监控、AI 指标、Token 分析、错误追踪 |

---

## ✨ 核心功能

### 💬 AI Chat Workspace
- 知识库问答模式（RAG 增强，自动标注引用来源）
- 普通闲聊模式（直接调用 LLM）
- Streaming 流式回复（SSE 打字机效果）
- 会话历史管理与知识库切换

### 📚 知识库管理
- 创建/删除知识库，文档上传与自动解析
- Chunk 切分配置（chunk_size / chunk_overlap）
- 向量化存储（ChromaDB），用户级别隔离

### 🔗 RAG Pipeline
```
Document → Parser → Chunker → Embedding → VectorStore → Retriever → Citation → LLM
```

### 🏢 企业管理 (v1.0.1 新增)
- Organization Console：组织信息与功能入口
- Members Management：组织成员管理与角色分配
- Departments：部门管理结构
- Knowledge ACL：知识库 4 级访问权限
- Quota Management：资源配额监控

### 🔐 安全中心 (v1.0.1 新增)
- Security Dashboard：安全状态总览
- Audit Logs：系统操作审计日志
- API Key 管理：密钥创建、撤销
- RBAC：ROOT / ADMIN / USER 三级权限

### 🤖 AI 能力中心 (v1.0.1 新增)
- Model Registry：AI 模型注册表管理
- Provider Management：多 Provider 状态查看
- Prompt Templates：提示词模板 CRUD 与版本管理
- AI Configuration：运行时配置概览
- Agents / Workflows / Tools：AI Agent 平台框架

### 📊 可观测性中心 (v1.0.1 新增)
- Monitoring Dashboard：系统 + AI 健康度监控
- AI Metrics：AI 调用指标与模型排行
- Token Analytics：Token 消耗趋势分析
- Error Tracking：错误追踪

---

## 🏗️ 技术栈

### 后端
| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI (Python 3.12) |
| ORM | SQLAlchemy 2.0 (Async) |
| 数据库 | SQLite (开发) / PostgreSQL (生产) |
| 迁移工具 | Alembic |
| 向量存储 | ChromaDB |
| 嵌入模型 | BAAI/bge-small-zh-v1.5 |
| 认证 | JWT + passlib |
| AI Provider | DeepSeek / Agens |

### 前端
| 组件 | 技术 |
|------|------|
| 框架 | React 18 |
| 语言 | TypeScript |
| 构建工具 | Vite |
| 样式 | Tailwind CSS |
| 状态管理 | Zustand |
| 动画 | framer-motion |
| 图标 | lucide-react |

### 部署
| 组件 | 技术 |
|------|------|
| 容器化 | Docker + Docker Compose |
| CI/CD | GitHub Actions |

---

## 📁 项目结构

```
knowledge_chat/
├── backend/
│   ├── app/
│   │   ├── api/           # API 路由 (admin/auth/chat/knowledge/...)
│   │   ├── auth/          # JWT 认证
│   │   ├── core/          # 配置、日志、异常、权限
│   │   ├── models/        # SQLAlchemy 数据模型
│   │   ├── schemas/       # Pydantic 请求/响应
│   │   ├── services/      # 业务逻辑 (llm/knowledge/retrieval/usage/...)
│   │   └── storage/       # 数据库 & 向量存储
│   ├── scripts/           # 工具脚本
│   └── tests/             # 166+ 测试
├── frontend/
│   └── src/
│       ├── api/           # API 调用层 (admin/organizations/knowledgeConfig/...)
│       ├── components/    # UI 组件 (admin/auth/Chat/Documents/Layout/...)
│       ├── pages/         # 27+ 页面 (admin/ai/knowledge/monitoring/organization/...)
│       ├── store/         # Zustand 状态管理
│       └── hooks/         # 自定义 Hooks
├── docs/                  # 项目文档
├── docker-compose.yml     # Docker 部署
├── CHANGELOG.md           # v2.0.0 更新日志
└── VERSION                # 版本号
```

---

## 🚦 快速启动

### 环境要求
- Python 3.12+
- Node.js 18+
- npm 9+

### 后端

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 编辑 .env 填入 API Key
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 初始化系统

```bash
# 设置 ROOT 密码并创建 ROOT 用户
cd backend
set ROOT_PASSWORD=your_secure_password
python scripts/create_root.py
```

### 访问
- **前端界面**: http://localhost:5173
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/health

### Docker 部署

```bash
docker-compose up -d
```

---

## 🔧 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | 数据库连接 | `sqlite+aiosqlite:///./knowledge.db` |
| `LLM_PROVIDER` | LLM 提供商 | `deepseek` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |
| `AGENS_API_KEY` | Agens API Key | - |
| `EMBEDDING_MODEL` | 嵌入模型 | `BAAI/bge-small-zh-v1.5` |
| `CACHE_BACKEND` | 缓存后端 | `memory` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

---

## 🧪 测试

```bash
# 后端测试 (166+ passed)
cd backend && pytest

# 前端构建验证
cd frontend && npm run build
```

---

## � 1.0.1 Release Notes

### 版本定位
v1.0.1 是面向首次上线与生产试运行的稳定发布版本，重点提升平台的可用性、部署体验与企业级能力的完整性。

### 主要更新
- 完善企业级知识库平台的核心能力，包括聊天、知识库管理、RAG 检索、引用标注与多模型支持
- 增强组织管理与知识库访问控制，支持组织、部门与私有级权限模型
- 补齐 AI 能力中心能力：Provider 管理、模型注册、Prompt 模板、运行时配置
- 增加安全与可观测能力：RBAC、API Key、审计日志、监控与指标分析
- 优化 Docker / Compose / Helm / Kubernetes 的部署与说明文档，提升上线体验
- 补充测试覆盖与基础文档，降低使用与维护门槛

### 适用场景
- 企业知识库问答场景
- 组织级知识管理与权限控制
- AI 能力中心试点部署与内部试用

---

## 📜 版本历史

- **v1.0.1** (2026-07-22) — 稳定发布版：补齐文档与部署体验，完善企业级知识库平台基础能力
- **v1.0.0** — RAG Pipeline、多 Provider、Prompt 管理、用户隔离

---

## 📄 许可证

MIT
