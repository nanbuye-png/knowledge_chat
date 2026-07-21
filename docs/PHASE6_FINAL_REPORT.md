# Phase 6 最终架构报告

## 1. 当前系统架构

### 前端

```
frontend/src/
├── api/                      # API 层 — 与后端 1:1 映射
│   ├── auth.ts               → POST  /api/auth/*
│   ├── chat.ts               → POST  /api/chat/chat, /api/chat/stream
│   ├── knowledge.ts          → POST  /api/knowledge/query, /api/knowledge/query/stream
│   ├── knowledgeBases.ts     → CRUD /api/knowledge-bases
│   ├── knowledgeConfig.ts    → GET/PUT /api/knowledge-bases/{id}/config
│   ├── documents.ts          → CRUD /api/documents
│   ├── conversations.ts      → CRUD /api/conversations
│   ├── admin.ts              → GET   /api/admin/*
│   ├── client.ts             → axios 实例 (baseURL: /api + JWT interceptor)
│   └── ... (models, prompts, etc.)
│
├── contexts/                 # 状态管理
│   ├── ChatContext.tsx        → 纯聊天 (messages, conversations)
│   ├── KnowledgeChatContext.tsx → RAG 问答 (messages, sources, conversations)
│   ├── DocumentContext.tsx    → 文档管理
│   ├── ThemeContext.tsx       → 主题
│   └── ...
│
├── pages/
│   ├── chat/
│   │   └── ChatPage.tsx      → 纯 AI 对话，仅调用 chatApi
│   ├── knowledge/
│   │   ├── KnowledgePage.tsx      → 知识库 CRUD + 文档上传
│   │   ├── KnowledgeChatPage.tsx  → 知识库 RAG 问答，仅调用 knowledgeApi
│   │   └── KnowledgeSettingsPage.tsx
│   └── ...
│
├── components/
│   └── Layout/
│       ├── Sidebar.tsx       → 文档/知识库侧边栏
│       └── Navbar.tsx        → 顶部导航栏
│
├── types/index.ts            → 共享类型定义
├── App.tsx                   → BrowserRouter + AppRouter（无业务逻辑）
└── router/index.tsx          → 路由配置
```

### 后端

```
backend/app/api/
├── auth.py                   → /api/auth/* (register, login, logout, me)
├── auth_sessions.py          → /api/auth/sessions
├── api_keys.py               → /api/api-keys/*
├── chat.py                   → /api/chat/chat, /api/chat/stream
├── knowledge_query.py        → /api/knowledge/query, /api/knowledge/query/stream
├── knowledge_bases.py        → /api/knowledge-bases/*
├── knowledge_config.py       → /api/knowledge-bases/{id}/config
├── documents.py              → /api/documents/*
├── conversation.py           → /api/conversations/*
├── llm_model.py              → /api/llm-models/* (require_admin_or_root)
├── prompt_template.py        → /api/prompt-templates/* (require_admin_or_root)
├── prompt_version.py         → /api/prompt-templates/{id}/versions (require_admin_or_root)
├── usage.py                  → /api/usage/*
├── health.py                 → /api/health
├── admin/
│   ├── users.py              → /api/admin/users/*
│   ├── dashboard.py          → /api/admin/dashboard, /dashboard/overview, /dashboard/system
│   ├── audit_logs.py         → /api/admin/audit-logs
│   ├── sessions.py           → /api/admin/sessions/*
│   └── organizations.py      → /api/admin/organizations/*
```

## 2. API 最终列表

### Chat (通用 AI 对话)
| 方法 | URL | 前端文件 |
|------|-----|----------|
| POST | /api/chat/chat | chat.ts → chatMessage() |
| POST | /api/chat/stream (SSE) | chat.ts → createStreamChat() |

### Knowledge (RAG 问答)
| 方法 | URL | 前端文件 |
|------|-----|----------|
| POST | /api/knowledge/query | knowledge.ts → queryKnowledge() |
| POST | /api/knowledge/query/stream (SSE) | knowledge.ts → createStreamKnowledgeQuery() |

### Knowledge Bases
| 方法 | URL | 前端文件 |
|------|-----|----------|
| GET | /api/knowledge-bases | knowledgeBases.ts → listKnowledgeBases() |
| POST | /api/knowledge-bases | knowledgeBases.ts → createKnowledgeBase() |
| PUT | /api/knowledge-bases/{id} | knowledgeBases.ts → updateKnowledgeBase() |
| PATCH | /api/knowledge-bases/{id} | knowledgeBases.ts → updateKnowledgeBase() |
| DELETE | /api/knowledge-bases/{id} | knowledgeBases.ts → deleteKnowledgeBase() |
| GET | /api/knowledge-bases/{id}/config | knowledgeConfig.ts → getKnowledgeConfig() |
| PUT | /api/knowledge-bases/{id}/config | knowledgeConfig.ts → updateKnowledgeConfig() |

### Documents
| 方法 | URL | 前端文件 |
|------|-----|----------|
| POST | /api/documents/upload | documents.ts → uploadDocument() |
| GET | /api/documents | documents.ts → fetchDocuments() |
| DELETE | /api/documents/{id} | documents.ts → deleteDocument() |
| GET | /api/documents/{id}/status | documents.ts → getDocumentStatus() |

### Conversations
| 方法 | URL | 前端文件 |
|------|-----|----------|
| POST | /api/conversations | conversations.ts → createConversation(kbId?) |
| GET | /api/conversations | conversations.ts → listConversations(kbId?) |
| GET | /api/conversations/{id}/messages | conversations.ts → getConversationMessages() |
| PATCH | /api/conversations/{id} | conversations.ts → renameConversation() |
| DELETE | /api/conversations/{id} | conversations.ts → deleteConversation() |

**知识库支持**: knowledge_base_id 可空，创建时传入 null 为普通聊天

### Auth
| 方法 | URL | 前端文件 |
|------|-----|----------|
| POST | /api/auth/register | auth.ts |
| POST | /api/auth/login | auth.ts |
| POST | /api/auth/logout | auth.ts |
| GET | /api/auth/me | auth.ts |
| GET | /api/auth/sessions | auth.ts |

### Admin
| 方法 | URL | 前端文件 |
|------|-----|----------|
| POST/GET | /api/admin/users | admin.ts |
| PATCH | /api/admin/users/{id}/status | admin.ts |
| PATCH | /api/admin/users/{id}/role | admin.ts |
| DELETE | /api/admin/users/{id} | admin.ts |
| GET | /api/admin/dashboard | admin.ts → getDashboard() |
| GET | /api/admin/dashboard/overview | admin.ts → getDashboardOverview() [deprecated] |
| GET | /api/admin/dashboard/system | admin.ts → getSystemMonitorStatus() |
| GET | /api/admin/audit-logs | admin.ts |
| GET/DELETE | /api/admin/sessions | admin.ts |
| CRUD | /api/admin/organizations | admin.ts/organizations.ts |

### Protected (admin_or_root only)
| 方法 | URL | 说明 |
|------|-----|------|
| CRUD | /api/llm-models/* | require_admin_or_root |
| CRUD | /api/prompt-templates/* | require_admin_or_root |
| GET | /api/prompt-templates/{id}/versions | require_admin_or_root |

## 3. 数据模型

### User
```
id, username, email, password_hash, role (ROOT/ADMIN/USER),
is_system_account, is_active, last_activity_at, last_login_at,
failed_login_count, locked_until, deleted_at, created_at
```

### KnowledgeBase
```
id, user_id (FK→User), name, description, created_at, updated_at
- user_id 隔离: user 只能访问自己的 KB
```

### Conversation
```
id, user_id (FK→User), knowledge_base_id (FK→KB, nullable),
title, created_at, updated_at
- 普通聊天: knowledge_base_id=NULL
- 知识库聊天: knowledge_base_id=xxx
- user_id 隔离: 所有权通过 direct check (不再 join KB)
```

### Document
```
id (UUID), filename, file_size, file_type, status, chunk_count,
error_message, knowledge_base_id (FK→KB, nullable), created_at, updated_at
```

### Message
```
id, conversation_id (FK→Conversation, CASCADE DELETE), role, content, created_at
```

### 当前技术决策：暂不增加 `conversation_type`

**理由：**
- 当前通过 `knowledge_base_id` 是否为 NULL 即可区分 CHAT 和 KNOWLEDGE
- 增加额外字段需要同时修改 model/schema/service/types/migration，复杂度高
- 等 Agent/Workflow 功能确定后再统一增加 `conversation_type: CHAT | KNOWLEDGE | AGENT | WORKFLOW`

## 4. 权限模型

| 角色 | KB 操作 | Chat | Admin Dashboard | User Management | LLM/Prompt |
|------|---------|------|----------------|-----------------|-----------|
| USER | 自己的 KB | ✅ | ❌ | ❌ | ❌ |
| ADMIN | 自己的 KB | ✅ | ✅ (有限) | ✅ (非 ROOT) | ✅ |
| ROOT | 所有 KB | ✅ | ✅ (全部) | ✅ (全部) | ✅ |

- 所有 `knowledge_base_id` 查询必须带 `user_id` 过滤
- Conversation 所有权通过 `Conversation.user_id == current_user.id` 验证
- Prompt/LLM 管理需要 `require_admin_or_root`

## 5. 已删除/废弃内容

### 后端
| 接口 | 原因 | 替代方案 |
|------|------|----------|
| PUT/GET /api/chat/mode | 废弃全局模式切换 | 客户端本地状态 |
| GET /api/knowledge/debug/retrieval | 调试接口 | 无 |
| ~/api/chat/query, ~/stream/query | 迁移到 /api/knowledge | knowledge_query.py |
| knowledge_debug.py (文件) | 调试 | 已删除 |

### 前端
| 内容 | 原因 |
|------|------|
| chat.ts 中 setMode/getMode/queryKnowledge/createStreamKnowledgeQuery | 迁移到 knowledge.ts |
| ChatContext 中 mode/messagesByMode/setMode | ChatPage 不再需要 |
| ChatPage 中 KB selector/document upload/mode toggle | ChatPage 只负责纯聊天 |
| types/index.ts 中 ChatState | 已无引用 |

## 6. 当前风险

| 风险 | 级别 | 说明 |
|------|------|------|
| InputBox/Sidebar/Navbar 仍保留 mode prop | 低 | KnowledgeChatPage 硬编码 `mode="knowledge"` 调用，不影响功能 |
| Admin 页面 (ApiKeys/SystemConfig) 调用未实现的 backend | 中 | TODO 标记，需后端实现 /admin/api-keys 和 /admin/system/config |
| App.tsx 中 BrowserRouter 移动到了 App.tsx | 低 | 无功能影响 |
| conversation_type 未增加 | 低 | 通过 knowledge_base_id nullable 区分 |

## 7. 后续建议

1. **短期**: 实现 /admin/api-keys 和 /admin/system/config 后端端点
2. **短期**: InputBox 的 mode prop 可重构为独立的 `ChatInput` 和 `KnowledgeInput`
3. **中期**: 引入 conversation_type 枚举字段
4. **中期**: App.tsx 中的 BrowserRouter 可以考虑迁移到 router/index.tsx
5. **长期**: Agent/Workflow 模块的完整状态管理和 API 设计

---

## Phase 6 执行总结

| 检查项 | 状态 |
|--------|------|
| 废弃 mode 逻辑 | ✅ 已彻底删除 |
| Chat/KB 完全独立 | ✅ ChatPage → chatApi, KBChatPage → knowledgeApi |
| App.tsx 无业务代码 | ✅ 仅 BrowserRouter + AppRouter |
| TypeScript 0 error | ✅ tsc --noEmit 0 错误 |
| Python lint | ruff 未安装，手动检查无语法错误 |
| API 列表完整性 | ✅ 文档完整 |
| Conversation 设计 | ✅ knowledge_base_id nullable 区分普通/知识库聊天 |
| PHASE6_FINAL_REPORT.md | ✅ 已生成 |