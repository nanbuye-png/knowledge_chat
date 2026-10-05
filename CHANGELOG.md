# 更新日志

## v1.0.1 (2026-09-30) — Reality Audit 整改（Phase 1–3）

基于 `docs/KNOWLEDGE_CHAT_REALITY_AUDIT.md`（审计基线 `a689bf2`）的实际修复，每个条目对应一个独立 commit。
后端测试基线：**235 passed → 659 passed**（`cd backend && python -m pytest -q`）。

### 安全 / 鉴权（P0）
- **知识库越权读修复** — 此前只在「无会话」分支校验知识库归属，导致「自己的会话 + 他人的 `knowledge_base_id`」可越权检索；现在两条分支统一校验知识库归属 + 会话归属 + 二者一致性（`4ac39e8`）
- **占位 SECRET_KEY 拒绝启动** — 生产环境使用默认占位密钥直接 fail-fast；`/docs`、`/redoc`、`/openapi.json` 按环境关闭（`3bb33f4`）
- **RBAC 全量 500 修复** — 权限联表 SQL 修复 + 遗留角色映射 + ROOT 授权收敛（`dd815fa`）
- **认证通道修复** — 拒绝已禁用/已删除用户的 token，修复 API Key 认证通道，统一 naive/aware UTC 处理（`d8ca420`）

### 契约与前端一致性
- **错误契约统一** — `/api/*` 的 500 不再拼接 `str(e)`（SQL/DSN/堆栈会顺响应泄漏），改为固定文案 + `code=INTERNAL_ERROR` + `request_id`，原始异常仅进日志（`0aa43bb`）
- **前端契约适配** — 按 Phase 3 后端契约调整前端解析（`760d383`）
- **工具层落地（最小真实路径）** — 新增 `kb_search`（复用生产检索链路 + 归属校验）与 `calculator`（AST 白名单，不使用 eval）两个真实工具，端点 `GET /api/tools`、`POST /api/tools/run`、`POST /api/tools/{tool_name}[/invoke]`，含超时 / 最大调用次数 / 失败处理；删除前端占位假数据，Agent / Workflow 页面统一标注 Planned（`474ebfa`）
- **前端空壳页面与死代码清理** — 删除会真实调用（且失败被 `catch` 吞掉）的 `AgentStudioPage` / `WorkflowStudioPage` 两个空壳编排器、`api/agents.ts` / `api/workflows.ts` 两个假客户端与无人引用的 `store/agent.ts` / `store/workflow.ts`；`/platform/agents`、`/platform/workflows` 保留为 redirect 到带 Planned 标注的 `/ai/agents`、`/ai/workflows`，侧边栏去掉重复入口（`fcacc25`）
- **Agent 最小真实路径落地（§4）** — 新增 `agents` 表（迁移 `9015d1a85a71`，含 user_id / knowledge_base_id / model_id 外键与工具白名单校验）、`/api/agents` 的 CRUD 与 `POST /api/agents/{id}/execute`；执行链是「确定性工具选择（`app/services/agent/planner.py`）→ 复用 `ToolRegistry.run_plan` 的超时/次数上限/失败即停 → 回答」，绑定模型时走真实 LLM Provider（`answer_mode=llm`），未绑定模型时如实返回 `tools_only`（工具结果汇总，不冒充模型生成）；工具失败/被丢弃的步骤出现在 `steps`/`warnings` 中而不是被吞掉。前端 `/ai/agents` 从 Planned 页改回真实页面（配置知识库/模型/工具 + 执行面板展示执行轨迹），README 与 `api/tools.ts`、`EnterpriseLayout` 注释同步；Workflow 仍未实现，继续标注 Planned（`b6bfdf9`）
- **Workflow 最小真实路径落地（§4）** — 新增 `workflows` 表（迁移 `73e4a02ed72e`）、`/api/workflows` 的 CRUD 与 `POST /api/workflows/{id}/execute`，以及 `app/services/workflow`（`templating.py` 状态传递 + 条件分支、`runner.py` 顺序执行、`errors.py` 错误契约）：步骤由用户**显式声明**（工具 / 参数 / `when` / `on_error`），参数支持 `{{input}}` 与 `{{steps.<步骤ID>.output.<字段>}}` 占位符（整个值就是一个占位符时保留原始类型），条件分支支持 `always` / `previous_succeeded` / `previous_failed` / `input_is_math`（复用 Agent 规划器的数学识别，不新增第二套判断），失败策略 `abort` / `continue`；工具执行复用 `/api/tools` 同一份 `ToolRegistry`（超时 / 参数校验 / 失败包装），被跳过的步骤带 `skip_reason`、失败步骤带 `error.code`，都不静默；写入口拦截未注册工具 / 重复步骤 id / 前向引用 / 超过 `WORKFLOW_MAX_STEPS`。前端删除 Planned 占位页，重写 `/ai/workflows`（步骤编辑器 + 执行轨迹 + 跳过/失败原因），新增真实客户端 `api/workflows.ts`；`init_db` 的 create_all 兜底补上 Agent / Workflow 模型注册，README / CHANGELOG / 审计 §14 / 各注释同步，并把 `test_tools.py`、`test_sprint31_ai_enhancement.py` 中"断言 Workflow 未实现"改为断言真实路由（本轮）
- **Workflow 参数补齐口径统一 + 工具 Schema 读取修复（2026-10-03）** — 前端此前按扁平结构读 `GET /api/tools` 的 `parameters`（它是标准 JSON Schema，参数规格在 `parameters.properties`），于是"按 Schema 预填默认参数"从未生效：页面新建的每个步骤参数都是 `{}`，calculator 靠后端补齐 `expression` 才跑通、`kb_search` 直接 `TOOL_INVALID_ARGUMENTS: 缺少必填参数: query`。现在统一从 `parameters.properties` 取规格并用 `ToolParameterSchema` 类型钉住结构、kb_search 步骤新增**知识库下拉**（`GET /api/knowledge-bases`）；后端把"缺失时按本次输入取用"的参数收敛成一份清单 `INPUT_FILLED_ARGUMENTS`（`calculator.expression` / `kb_search.query`），执行器补齐、写入口校验、前端提示共用同一口径（不再出现"一个留空能跑、一个留空必失败"），并在写入口拦截必然失败的配置：`kb_search` 缺 `knowledge_base_id`（数据归属，不能替用户猜）→ 400 并给出照做的写法

### 工程 / 数据
- **`api_keys` 表缺失修复** — 迁移文件此前是空桩（`upgrade()/downgrade()` 均为 `pass`），现由迁移建表；不再手工维护模型 import 列表（`4c24dc5`）
- **评测产物归档口径** — 只归档正式评测报告，忽略 smoke 产物（`ccb1c86`）

### 部署 / 文档
- **镜像与 Compose** — 补 `.dockerignore`、健康检查、前端镜像 SPA rewrite（`80f36ba`）
- **Nginx / K8s** — 上传体积与 `X-Forwarded-For` 加固、补 `pvc.yaml`、后端固定单副本（`df585ba`）
- **文档口径修正** — Helm Chart 与 Grafana 栈明确标注 Planned（`65920af`）；README 的「Agents / Workflows / Tools」措辞修正为「工具层已实现 + Agent/Workflow Planned」

### 测试
- 新增 `tests/test_tools.py`（工具端点 / 注册表 / 前端 Planned 文本契约）、`tests/test_error_contract.py`（500 不泄漏 + 统一契约）等；前端契约新增「空壳页面与假 API 客户端必须不存在、旧 URL 必须 redirect」断言（`fcacc25`）；按审计 §4 删除 `test_sprint31` 内与生产无关的玩具
  `Tool` / `Workflow` / `Agent` 类，改为断言「未实现」这一事实
- 新增 `tests/test_agents.py`（29 例）：`agents` 表 CRUD 与归属校验（非本人一律 404）、
  配置校验（未注册工具 / 他人知识库 / 假模型 / 超上限调用次数 → 400）、规划器单测
  （数学意图识别的正反例、计划顺序、`max_tool_calls` 截断与 `warnings`）、执行覆盖
  （`tools_only` 与 `llm` 两种回答来源、`top_k` 透传、停用 409、无能力 400、工具失败
  200 + `steps[].error` 且不泄漏内部细节、LLM 故障 502 + `request_id`、模型被禁用
  400 而不是静默降级）；`test_sprint31` 的 `TestAgent` 改为断言「路由存在 + 执行器
  复用生产 `ToolRegistry` + 无玩具类残留」；`test_tools.py` 的前端契约改为
  「Agent 页必须打真实 `/api/agents`（且不得再出现 PlannedNotice / 假数据）、
  Workflow 侧继续禁止假客户端复活」

### CI 全绿修复（2026-10-05）— 让"本地绿 / CI 红"的四类环境依赖归零

上一次 CI（`bc70930`）失败 8 例（733 passed / 8 failed），逐条定位到的都是"测试依赖本机环境"：

- **语料 sha256 被行尾绑架** — `wuxi_culture_palace_faq.txt` 在 Windows 检出是 CRLF、CI 上是 LF，同一份语料算出两个哈希 → `sha256_of()` 改为**先按 LF 归一化再算**（正文改动仍然抓得到），清单里的哈希 / 字节数同步为归一键值
- **清单引用了仓库不跟踪的文件** — `docs/INTERVIEW_GUIDE.md` 在 `.gitignore` 里，干净检出必然"语料文件不存在" → 清单新增 `optional: true` 语义，`load_corpus()` 对缺席的**可选**语料直接跳过（本机存在时仍按干扰项计入，评测口径不变）
- **流式接口自带的 session 打到了真实库** — `/api/chat/stream`、`/api/knowledge/query/stream` 用的是 `async with async_session() as db:` 而不是 `Depends(get_db)`，只覆盖 `get_db` 时它们指向 CI 上的空库（`no such table: users`）；`conftest.client` 现在把每个 `app.*` 模块持有的 `async_sessionmaker` 一并重绑到临时库（按类型判断，兼容 `test_db_migration` 的 `importlib.reload`）
- **限流配置被"世代"割裂** — `test_connection_pool` / `test_db_migration` / `test_provider_factory` 会 `importlib.reload(app.core.config)`，每 reload 一次就换一个 `Settings` 对象，而运行期才 import 的 `app.core.rate_limit` 绑的是旧对象、测试改的是本模块收集期那份 → 整包跑第二次请求不是 429（单跑该文件却是绿的）；`test_rate_limit_unified` 改为把补丁打到所有持有 `settings` 引用的模块
- **检索缓存跨用例串味** — 缓存 fingerprint 不含重排器，进程级缓存（CI 上是 Redis）让"同一个查询、换一个重排器"的用例互相命中 → `test_reranker` 的链路用例显式 `RetrievalCache(enabled=False)`
- **README 口径** — Agents / Workflows 补回"最小真实路径（已实现）"的措辞，与 `test_tools.py` 的前端契约断言一致

验证：`cd backend && python -m pytest -q`（含 CI 的 `DATABASE_TYPE=sqlite` / `DATABASE_URL=sqlite+aiosqlite:///./test.db` 组合）**742 passed**；前端 `npm run build` 通过

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