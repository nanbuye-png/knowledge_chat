# 更新日志

## v1.0.1 (2026-09-30) — Reality Audit 整改（Phase 1–3）

基于 `docs/KNOWLEDGE_CHAT_REALITY_AUDIT.md`（审计基线 `a689bf2`）的实际修复，每个条目对应一个独立 commit。
后端测试基线：**235 passed → 629 passed**（`cd backend && python -m pytest -q`）。

### 安全 / 鉴权（P0）
- **知识库越权读修复** — 此前只在「无会话」分支校验知识库归属，导致「自己的会话 + 他人的 `knowledge_base_id`」可越权检索；现在两条分支统一校验知识库归属 + 会话归属 + 二者一致性（`4ac39e8`）
- **占位 SECRET_KEY 拒绝启动** — 生产环境使用默认占位密钥直接 fail-fast；`/docs`、`/redoc`、`/openapi.json` 按环境关闭（`3bb33f4`）
- **RBAC 全量 500 修复** — 权限联表 SQL 修复 + 遗留角色映射 + ROOT 授权收敛（`dd815fa`）
- **认证通道修复** — 拒绝已禁用/已删除用户的 token，修复 API Key 认证通道，统一 naive/aware UTC 处理（`d8ca420`）

### 契约与前端一致性
- **错误契约统一** — `/api/*` 的 500 不再拼接 `str(e)`（SQL/DSN/堆栈会顺响应泄漏），改为固定文案 + `code=INTERNAL_ERROR` + `request_id`，原始异常仅进日志（`0aa43bb`）
- **前端契约适配** — 按 Phase 3 后端契约调整前端解析（`760d383`）
- **工具层落地（最小真实路径）** — 新增 `kb_search`（复用生产检索链路 + 归属校验）与 `calculator`（AST 白名单，不使用 eval）两个真实工具，端点 `GET /api/tools`、`POST /api/tools/run`、`POST /api/tools/{tool_name}[/invoke]`，含超时 / 最大调用次数 / 失败处理；删除前端占位假数据，Agent / Workflow 页面统一标注 Planned（`474ebfa`）

### 工程 / 数据
- **`api_keys` 表缺失修复** — 迁移文件此前是空桩（`upgrade()/downgrade()` 均为 `pass`），现由迁移建表；不再手工维护模型 import 列表（`4c24dc5`）
- **评测产物归档口径** — 只归档正式评测报告，忽略 smoke 产物（`ccb1c86`）

### 部署 / 文档
- **镜像与 Compose** — 补 `.dockerignore`、健康检查、前端镜像 SPA rewrite（`80f36ba`）
- **Nginx / K8s** — 上传体积与 `X-Forwarded-For` 加固、补 `pvc.yaml`、后端固定单副本（`df585ba`）
- **文档口径修正** — Helm Chart 与 Grafana 栈明确标注 Planned（`65920af`）；README 的「Agents / Workflows / Tools」措辞修正为「工具层已实现 + Agent/Workflow Planned」

### 测试
- 新增 `tests/test_tools.py`（工具端点 / 注册表 / 前端 Planned 文本契约）、`tests/test_error_contract.py`（500 不泄漏 + 统一契约）等；按审计 §4 删除 `test_sprint31` 内与生产无关的玩具
  `Tool` / `Workflow` / `Agent` 类，改为断言「未实现」这一事实

## v1.0.1 (2026-09-22)

### LLM 模型升级：agnes-2.5-flash

- **默认模型切换** — `LLM_PROVIDER=agens` + `LLM_MODEL=agnes-2.5-flash`（`.env` / `backend/.env` / `.env.production.local`）
- **配置自检** — 新增 `Settings.check_llm_config()`，启动时校验 Provider / 模型名前缀 / API Key 一致性并输出告警；启动日志新增当前 LLM 模型
- **推理型模型适配** — `AgensProvider` 忽略 `reasoning_content` 增量并去除正文首部前导换行（流式 + 非流式）
- **日志健壮性** — 控制台日志在 GBK 环境下自动切换 UTF-8，修复 emoji 触发的 `UnicodeEncodeError` 日志中断
- **配套更新** — 前端模型名称/占位符、Docker Compose、K8s ConfigMap/Secret、Helm values、README、`docs/provider_system.md`
- **测试** — 新增 `backend/tests/test_llm_config.py`（19 个用例），后端全量 209 个用例通过

详细报告：`docs/AGNES_2.5_FLASH_UPGRADE_REPORT.md`

## v1.0.1 (2026-07-22)

### 版本概述
这是面向首次上线与生产试运行的稳定发布版本，重点提升平台的可用性、部署体验与企业级能力的完整性。

### 主要更新
- 完善企业 AI 知识库平台的核心能力，包括聊天、知识库管理、RAG 检索、引用标注与多模型支持
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

## v1.0.1 (2026-07-19)

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