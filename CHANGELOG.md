# 更新日志

## v2.0.0 (2026-07-19)

### 新增功能

#### 企业管理后台 (Sprint 36)
- **Admin Dashboard** — 系统概览仪表盘，展示核心指标、用户统计、内容统计、系统监控、环境信息
- **User Management** — 用户管理后台，支持用户搜索、角色筛选、状态筛选、分页、启用/禁用、修改角色、删除用户
- **Online Monitor** — 在线用户实时监控，支持 15 秒自动刷新、在线率统计、活跃状态展示
- **Usage Analytics** — 使用分析面板，展示 Token 消耗、调用次数、费用统计、模型排行

#### 组织管理 (Sprint 37)
- **Organization Console** — 企业管理空间，组织信息展示与功能模块入口
- **Members Management** — 组织成员管理，支持成员列表、角色修改(OWNER/ADMIN/MEMBER)、移除成员
- **Departments** — 部门管理框架页面
- **ManagerRoute** — 新增 ROOT + ADMIN 权限路由组件

#### 知识库企业化管理 (Sprint 38)
- **Knowledge ACL** — 知识库权限管理 UI，支持 4 级访问级别（公开/组织/部门/私有）
- **Quota Management** — 企业配额管理，使用概览与进度条配额展示
- **Knowledge Settings** — 知识库 AI 参数配置（Chunk Size / Overlap / Embedding Model / Top K）

#### AI 能力管理中心 (Sprint 39)
- **Model Registry** — AI 模型注册表管理，支持模型 CRUD、启用/禁用
- **Provider Management** — AI Provider 管理，Provider 卡片展示
- **Prompt Management** — 提示词模板管理，支持 CRUD、激活/停用
- **AI Configuration** — AI 运行时配置概览

#### 安全中心 (Sprint 40)
- **Security Dashboard** — 安全状态总览，用户统计卡片 + 账号安全状态表
- **Audit Logs** — 增强版审计日志，支持操作类型筛选、分页

#### Agent 与工作流 (Sprint 41)
- **Agents Console** — AI Agent 管理框架页面
- **Workflows Console** — 工作流管理框架页面
- **Tool Registry** — 工具注册表框架页面

#### 可观测性中心 (Sprint 42)
- **Monitoring Dashboard** — 系统监控首页，CPU/内存/磁盘 + AI 健康度 + 服务状态
- **AI Metrics** — AI 调用指标与模型分析
- **Token Analytics** — Token 消耗趋势分析
- **API Performance** — API 接口性能监控框架
- **Error Tracking** — 错误追踪（基于审计日志）

### 功能改进

- **Sidebar 重构** — 分为 Administration / Enterprise / Knowledge / AI Center / Monitoring 五大区域
- **统一权限模型** — AdminRoute (ROOT only) + ManagerRoute (ROOT + ADMIN)
- **统一 UI 风格** — 卡片、表格、Badge、Modal、Loading/Error/Empty 状态统一
- **Redis 客户端修复** — 强制 RESP2 协议，兼容旧版 Redis
- **DATABASE_URL 修复** — 修复 Windows 环境下 SQLAlchemy URL 解析问题

### 技术架构

- **后端**: FastAPI (Python 3.12) + SQLAlchemy 2.0 (Async) + SQLite/PostgreSQL
- **前端**: React 18 + TypeScript + Vite + Tailwind CSS + Zustand + framer-motion
- **AI**: Multi LLM Provider (DeepSeek / Agens) + RAG Pipeline + ChromaDB
- **安全**: JWT + RBAC + Audit Log + Rate Limit + API Key
- **部署**: Docker + Docker Compose