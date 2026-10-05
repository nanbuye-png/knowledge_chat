import sys
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import os


# 计算项目 backend 目录（从此文件向上 3 级: core/config.py -> app -> backend）
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _make_absolute(path: str) -> str:
    """将相对路径转换为以 backend 目录为根的绝对路径（使用正斜杠，兼容 SQLAlchemy URL）。"""
    p = Path(path)
    if p.is_absolute():
        # Windows 绝对路径（如 D:\xxx）转换为正斜杠，兼容 SQLAlchemy URL
        return p.as_posix()
    return (_BACKEND_DIR / p).as_posix()


# ---- LLM Provider / 模型元数据（用于配置校验与文档提示） ----
# 已支持的 Provider（规范键 = 厂商品牌名，与模型 ID ``agnes-*`` 一致）
LLM_PROVIDERS: tuple[str, ...] = ("deepseek", "agnes")

# 每个 Provider 的模型名前缀（用于校验 LLM_PROVIDER 与 LLM_MODEL 是否匹配）
PROVIDER_MODEL_PREFIXES: dict[str, str] = {
    "deepseek": "deepseek",
    "agnes": "agnes",
}

# 各 Provider 的已知模型名（可通过 GET {AGNES_API_BASE}/models 查询）
KNOWN_MODELS: dict[str, tuple[str, ...]] = {
    "deepseek": ("deepseek-chat", "deepseek-reasoner"),
    "agnes": (
        "agnes-2.0-flash",
        "agnes-2.5-flash",
        "agnes-2.5-pro",
        "agnes-2.5-pro-beta",
        "agnes-2.5-pro-alpha",
        "agnes-3.0-flash",
    ),
}

# Provider 名称别名表：把「历史写法 / 手填拼写」收敛到规范键 ``agnes``。
#
# 实测缺陷（Agent / 工作流报「Agent 生成回答失败」）：
# 代码里的 Provider 键曾写作 ``agens``（字母顺序写反），而厂商品牌名、模型 ID
# （``agnes-2.5-flash``）与 Base URL（apihub.agnes-ai.com）都是 ``agnes``。
# 用户在「Model Registry」按品牌名填 ``agnes`` 时被工厂拒绝：
# ``LLMProviderFactory.create_from_model()`` 抛 ``Unknown LLM provider: 'agnes'``，
# 而 Agent 层对外只回一句通用文案，排查成本极高（实测就是这么踩的）。
# 现规范键统一为 ``agnes``；历史 ``agens`` 保留为别名，避免已有 .env / 数据库 /
# 部署清单立刻失效（库内历史值由迁移 ``b7c1d5e9a3f2`` 一次性收敛）。
PROVIDER_ALIASES: dict[str, str] = {
    "agnes": "agnes",
    "agens": "agnes",
    "agness": "agnes",
    "agnes-ai": "agnes",
    "agnesai": "agnes",
    "deepseek": "deepseek",
    "deep-seek": "deepseek",
    "deepseek-ai": "deepseek",
}


def normalize_provider(name: str | None) -> str:
    """把 Provider 名称收敛为规范键（去空白、转小写、解析别名）。

    Args:
        name: 用户输入的 Provider 名称，例如 ``" Agnes "``。

    Returns:
        规范键（如 ``"agnes"``）；未登记的写法原样返回（交由调用方判定是否支持，
        便于上层给出"可选值: ..."的明确报错）。
    """
    key = (name or "").strip().lower()
    return PROVIDER_ALIASES.get(key, key)


# ---------------------------------------------------------------------------
# 安全常量（审计 §6.1）
# ---------------------------------------------------------------------------
# 默认 SECRET_KEY 是**仓库里的公开值**：用它签发 JWT 等于把 ROOT 权限公开
# （任何人都能自签 token）。因此生产环境启动时 fail-fast 拒绝启动，
# 开发/测试环境只告警。改这个值必须同步更新 PLACEHOLDER_SECRET_KEYS。
DEFAULT_SECRET_KEY = "knowledge-chat-secret-key-change-in-production"

# 已知占位串：仓库里的模板/脚手架用过这些值，任何一个出现在生产环境都视为
# 「没配置」。含 .env.production、docker-compose.yml、k8s/secret.yaml 的示例。
PLACEHOLDER_SECRET_KEYS: frozenset[str] = frozenset({
    DEFAULT_SECRET_KEY,
    "knowledge-chat-secret-change-in-production",
    "change-me-to-a-random-secret",
    "your-secret-key-change-in-production",
    "your-secret-key",
    "change-me",
    "changeme",
    "secret",
    "dev-only-insecure-secret-key-not-for-production",
})

# 最短 SECRET_KEY（字节）。HS256 的强度完全取决于这个字符串的熵，
# `openssl rand -hex 32` = 64 字符。
MIN_SECRET_KEY_BYTES = 32


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "智能知识库问答系统"
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"  # development | production | testing

    # LLM 提供商（规范键：deepseek 或 agnes；历史写法 agens 会自动归一）
    LLM_PROVIDER: str = "deepseek"

    # DeepSeek 配置
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"

    # 当前使用的模型（随 LLM_PROVIDER 切换），如 deepseek-chat / agnes-2.5-flash
    LLM_MODEL: str = "deepseek-chat"

    # Agnes 配置（规范变量名；历史 AGENS_API_KEY / AGENS_API_BASE 仍可读取）
    AGNES_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("AGNES_API_KEY", "AGENS_API_KEY"),
    )
    AGNES_API_BASE: str = Field(
        default="https://apihub.agnes-ai.com/v1",
        validation_alias=AliasChoices("AGNES_API_BASE", "AGENS_API_BASE"),
    )

    # ---- LLM HTTP 客户端（代理开关 / 超时）----
    # 当系统代理（如 Clash 的 127.0.0.1:7897）干扰 LLM API 连接时设为 True，
    # 让 LLM 请求绕过系统/环境代理直连（trust_env=False）。
    LLM_DISABLE_PROXY: bool = False
    # LLM 请求超时（秒）：作用于流式响应的 read/write 阶段
    LLM_TIMEOUT: float = 120.0
    # LLM 连接/连接池超时（秒）
    LLM_CONNECT_TIMEOUT: float = 10.0

    # ---- 数据库 ----
    # 数据库类型: "sqlite" 或 "postgresql"
    DATABASE_TYPE: str = "sqlite"

    # 当 DATABASE_TYPE = "sqlite" 时生效
    DATABASE_URL: str = "sqlite+aiosqlite:///./knowledge.db"

    # 当 DATABASE_TYPE = "postgresql" 时生效
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "knowledge_chat"

    # 连接池配置（仅 PostgreSQL 使用）
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE: int = 3600

    # ---- 基础设施 Provider 配置 ----
    # 缓存后端: "memory" | "redis"
    CACHE_BACKEND: str = "memory"

    # Worker 后端: "local" | "celery" (未来)
    WORKER_BACKEND: str = "local"

    # 向量存储
    VECTOR_STORE_TYPE: str = "chroma"  # chroma 或 qdrant
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    COLLECTION_NAME: str = "documents"
    # bge-small-zh-v1.5 的输出维度是 512（原先误写为 768）。
    # 该值仅作为提供者默认维度使用；向量库按实际写入维度建索引。
    EMBEDDING_DIM: int = 512

    # 嵌入
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # 文件上传
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: set = {
        ".pdf", ".docx", ".doc", ".md", ".txt", ".xlsx", ".csv"
    }

    # 分块
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100

    # ---- 检索模式（Phase 1 §5.2 Hybrid Retrieval）----
    # vector = 仅向量检索（**Phase 2 评测的 Baseline**）
    # hybrid = 向量 + BM25 稀疏检索加权融合
    RETRIEVAL_MODE: str = "hybrid"
    # 召回分下限：低于该分数的 chunk 不进入上下文（也不进入 Reranker）。
    # 注意两种检索模式的分数含义不同：
    #   vector 模式 = 余弦相似度（1 - 余弦距离）
    #   hybrid 模式 = 两通道归一化后的加权融合分（0.5*vector + 0.5*bm25）
    # 因此该阈值需要按模式分别标定（见 docs/RAG_EVALUATION.md）。
    RETRIEVAL_MIN_SCORE: float = 0.3
    # 融合权重（可配置；默认等权）
    HYBRID_VECTOR_WEIGHT: float = 0.5
    HYBRID_BM25_WEIGHT: float = 0.5
    # 每条召回通道的候选数（Recall 阶段），最终 top_k 由 Context 阶段决定
    HYBRID_RECALL_K: int = 20
    # 稀疏索引（倒排）持久化文件；与向量库同级存放
    SPARSE_INDEX_PATH: str = "./chroma_db/sparse_index.db"
    # BM25 参数
    SPARSE_BM25_K1: float = 1.5
    SPARSE_BM25_B: float = 0.75
    # 稀疏索引不可用时是否允许回退为纯向量检索（保证服务不中断）
    SPARSE_INDEX_FALLBACK: bool = True

    # ---- Reranker（Phase 1 §5.3）----
    # Retriever 负责 Recall，Reranker 负责 Precision
    RERANKER_ENABLED: bool = True
    # lexical（零依赖词项重叠，默认，CI 可稳定运行）
    # cross_encoder（本地 bge-reranker，精度更高，需下载模型）
    RERANKER_TYPE: str = "lexical"
    RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    # 送入重排的候选数（Recall 阶段规模）
    RERANKER_CANDIDATES: int = 20
    # 重排后进入 Context 的数量
    RERANKER_TOP_K: int = 5
    # 单次重排超时（秒）——超时即回退召回顺序
    RERANKER_TIMEOUT: float = 10.0
    RERANKER_BATCH_SIZE: int = 16

    # ---- Context Filtering（Phase 1 §5.4）----
    # 低于该分数的 chunk 不进入 LLM；<= 0 表示不启用过滤。
    # 分数区间：rerank_score ∈ [0,1]（lexical 重叠率 / cross-encoder sigmoid），
    # 召回 score 为融合分（∈[0,1]）。建议启用时取 0.1~0.3。
    CONTEXT_SCORE_THRESHOLD: float = 0.0
    # 分数来源：auto（优先 rerank_score，缺失回退 score）/ rerank / retrieval
    CONTEXT_SCORE_SOURCE: str = "auto"

    # ---------- 异步入库（P0-4）----------
    # Worker 并发上限（每个任务一个后台线程，超出则排队）
    WORKER_MAX_CONCURRENCY: int = 4

    # ---- 异步入库（P0-4）----
    # True：上传后立即返回，由后台 Worker 完成解析/切分/向量化（默认）
    # False：在请求内同步处理（便于少数需要确定性结果的场景/测试）
    DOCUMENT_PROCESSING_ASYNC: bool = True

    # ---- 上传幂等（Phase 3 §5.3）----
    # True：同一知识库内上传内容完全相同的文件时跳过重复处理
    #   （命中已完成/处理中的记录 → 直接返回既有记录；命中 FAILED 记录 →
    #   复用该记录重跑，而不是留下两条永远失败的记录）
    # False：关闭去重，每次上传都新建记录（排障/压测时用）
    DOCUMENT_DEDUP_ENABLED: bool = True

    # ---- 统一重试（Phase 3 §5.2）----
    # 总开关：false 时所有重试退化为单次调用（便于压测/排障时对比）
    RETRY_ENABLED: bool = True
    # 总尝试次数（含首次调用）：3 表示最多重试 2 次
    RETRY_MAX_ATTEMPTS: int = 3
    # 首次重试前的等待秒数（指数退避起点）
    RETRY_BASE_DELAY: float = 1.0
    # 单次等待上限（秒），防止退避无限增长
    RETRY_MAX_DELAY: float = 30.0
    # 退避倍数（2.0 → 1s, 2s, 4s, ...）
    RETRY_BACKOFF_FACTOR: float = 2.0
    # 抖动比例（±20%），避免多任务同时重试再次撞上限流
    RETRY_JITTER: float = 0.2
    # 按调用类型覆盖尝试次数（0 = 沿用 RETRY_MAX_ATTEMPTS）
    LLM_RETRY_MAX_ATTEMPTS: int = 3
    EMBEDDING_RETRY_MAX_ATTEMPTS: int = 3
    # 文档级（整篇入库）重试：次数少、退避长，避免与调用级重试叠乘
    TASK_RETRY_MAX_ATTEMPTS: int = 2
    TASK_RETRY_BACKOFF_S: float = 5.0
    TASK_RETRY_MAX_BACKOFF_S: float = 60.0

    # ---- 可观测性（Phase 3 §5.6）----
    # Prometheus 指标中间件开关（/metrics 路由本身始终注册）。
    # false 时不采集请求级指标（排障时减少噪声）。
    METRICS_ENABLED: bool = True

    # ---- 检索结果缓存（Phase 3 §5.4）----
    # True：同一知识库 + 同查询 + 同历史 + 同参数的检索结果直接复用
    #   （文档入库完成 / 删除 / 重跑时按知识库整体失效）
    RETRIEVAL_CACHE_ENABLED: bool = True
    # 检索缓存 TTL（秒）；文档变化会立即失效，所以 TTL 只用来兜底陈旧数据
    RETRIEVAL_CACHE_TTL: int = 300

    # ---- 反向代理（Phase 3 §5.4 限流取真实 IP）----
    # 信任的反向代理层数：取 X-Forwarded-For 右数第 N 个值作为客户端 IP。
    # nginx 使用 $proxy_add_x_forwarded_for 时，客户端可伪造左侧字段，
    # 只有最右侧（由我们信任的代理写入）才可信。
    TRUSTED_PROXY_COUNT: int = 1

    # ---- Abstention / 拒答（Phase 1 §5.6）----
    # 无足够依据时拒答，而不是让 LLM 猜测
    ABSTENTION_ENABLED: bool = True
    ABSTENTION_MESSAGE: str = "当前知识库中没有找到足够的信息来回答该问题。"
    # 有效上下文 chunk 数下限（低于则拒答）
    ABSTENTION_MIN_CONTEXT_CHUNKS: int = 1
    # 最高召回分下限；<= 0 表示不按分数拒答（仅保留"无上下文"拒答）
    ABSTENTION_SCORE_THRESHOLD: float = 0.0
    # 最高重排分下限；<= 0 表示不启用
    ABSTENTION_RERANK_THRESHOLD: float = 0.0

    # ---- Query Rewrite（Phase 1 §5.1）----
    # 用 LLM 把用户提问改写为更适合检索的独立查询（补全指代、省略主语）。
    # 任何失败（超时/异常/输出非法）都会回退到原始 Query，不影响问答。
    QUERY_REWRITE_ENABLED: bool = True
    # 单次改写的超时（秒）——超时即回退，绝不阻塞问答链路
    QUERY_REWRITE_TIMEOUT: float = 10.0
    # 参与改写的最近对话轮数（每轮 = 一条 user/assistant 消息）
    QUERY_REWRITE_MAX_HISTORY: int = 4
    # 短于该长度的查询直接跳过改写（信息量不足以改写）
    QUERY_REWRITE_MIN_CHARS: int = 4
    # 改写结果的最大长度，超出视为非法输出并回退
    QUERY_REWRITE_MAX_CHARS: int = 200

    # ---- 工具调用（审计 §4：Agent / Workflow / Tools 的最小真实路径）----
    # 只做「工具」这一层：可被选择的工具（自带参数 Schema）+ 可执行的调用端点。
    # Agent 由 app/services/agent、Workflow 由 app/services/workflow 以薄层复用这些
    # 工具（超时 / 参数校验 / 失败处理全部在这里兜底，见各自 *_* 配置）。
    # 单次工具执行的超时（秒）；超时按 504 返回，绝不无限挂起
    TOOL_TIMEOUT_SECONDS: float = 15.0
    # 一次请求内最多执行的工具调用次数（POST /api/tools/run 的硬上限）
    TOOL_MAX_CALLS_PER_REQUEST: int = 5
    # kb_search 返回片段数上限（防止把整库内容塞进一次响应）
    TOOL_KB_SEARCH_MAX_TOP_K: int = 20
    # kb_search 每个片段的正文截断长度（字符）
    TOOL_KB_SEARCH_SNIPPET_CHARS: int = 500
    # calculator 表达式长度上限（字符）
    TOOL_CALCULATOR_MAX_CHARS: int = 200

    # ---- Agent 执行（审计 §4：Agent 的最小真实路径）----
    # Agent 只是"工具选择 + 受限执行 +（可选）LLM 汇总"的薄层：
    # 工具超时 / 次数上限 / 失败处理全部复用 app/services/tools。
    # 新建 Agent 时的默认单次工具调用上限（不能超过 TOOL_MAX_CALLS_PER_REQUEST）
    AGENT_DEFAULT_MAX_TOOL_CALLS: int = 3
    # Agent 执行时送给 LLM 的最大知识库片段数（防止上下文无限膨胀）
    AGENT_ANSWER_MAX_SNIPPETS: int = 5
    # Agent 执行时每个片段的正文截断长度（与 TOOL_KB_SEARCH_SNIPPET_CHARS 独立）
    AGENT_ANSWER_SNIPPET_CHARS: int = 300

    # ---- Workflow 编排（审计 §4：Workflow 的最小真实路径）----
    # Workflow = 用户显式声明的有序步骤 + 条件分支 + 状态传递 + 失败处理
    # （app/services/workflow）；工具超时 / 参数校验 / 异常包装复用 tools 层。
    # 一条 Workflow 最多多少步（创建时由 Schema 校验，执行时再兜底一次）
    WORKFLOW_MAX_STEPS: int = 5

    # ---- RAG 评测（Phase 2，见 backend/evaluation/README.md）----
    # 裁判模型单次最大 token。Agnes 的 agnes-2.5-flash 属于推理型模型，
    # 会先消耗 token 输出 reasoning_content，留太小会导致正文为空。
    EVAL_JUDGE_MAX_TOKENS: int = 800
    # 裁判温度（0 = 尽量确定性）
    EVAL_JUDGE_TEMPERATURE: float = 0.0
    # 裁判调用重试次数（429 限流 / 5xx / 超时等瞬时错误，以及空正文/非 JSON 输出）。
    # 免费额度下实测 71 题里有 20 题因 429 丢掉判分，故必须重试；
    # 非瞬时错误（参数/鉴权）不会重试。
    EVAL_JUDGE_RETRY: int = 4
    # 瞬时错误的重试基础退避秒数（指数退避：3s → 6s → 12s，上限 30s）
    EVAL_JUDGE_RETRY_DELAY: float = 3.0
    # 不可用输出（空正文 / 非 JSON）的重试间隔秒数（无需长退避）
    EVAL_JUDGE_OUTPUT_RETRY_DELAY: float = 1.0

    # JWT 认证
    # 默认值是**公开占位串**（审计 §6.1）：开发环境开箱可用，生产环境启动时会
    # 被 assert_secure_config() 拒绝（fail-fast），必须换成 openssl rand -hex 32。
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24
    # 是否暴露 /docs、/redoc、/openapi.json（None = 按 ENVIRONMENT 推断：
    # production 关闭，其余开启）。审计 §6.1-7「暴露面」。
    ENABLE_API_DOCS: bool | None = None

    # 跨域
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000", "http://localhost"]

    # 速率限制
    RATE_LIMIT_WINDOW: int = 60              # 默认限流窗口（秒）
    RATE_LIMIT_LOGIN: int = 5                # 登录接口每分钟最大请求数
    RATE_LIMIT_CHAT: int = 20                # 聊天接口每分钟最大请求数
    RATE_LIMIT_UPLOAD: int = 10              # 上传接口每分钟最大请求数

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    # ------------------------------------------------------------------
    # 安全配置（审计 §6.1）
    # ------------------------------------------------------------------

    # ---- 历史变量名兼容（已废弃，仅为外部脚本保留属性访问）----
    @property
    def AGENS_API_KEY(self) -> str:  # noqa: N802 — 历史拼写，仅兼容保留
        """已废弃：请使用 ``AGNES_API_KEY``（``AGENS_API_KEY`` 环境变量仍可读取）。"""
        return self.AGNES_API_KEY

    @property
    def AGENS_API_BASE(self) -> str:  # noqa: N802 — 历史拼写，仅兼容保留
        """已废弃：请使用 ``AGNES_API_BASE``（``AGENS_API_BASE`` 环境变量仍可读取）。"""
        return self.AGNES_API_BASE

    @property
    def is_production(self) -> bool:
        """是否生产环境（ENVIRONMENT 大小写、空格不敏感）。"""
        return self.ENVIRONMENT.strip().lower() == "production"

    @property
    def docs_enabled(self) -> bool:
        """是否暴露 /docs、/redoc、/openapi.json（审计 §6.1-7）。

        显式配置 ``ENABLE_API_DOCS`` 优先；未配置时按环境推断：生产关闭。
        """
        if self.ENABLE_API_DOCS is not None:
            return self.ENABLE_API_DOCS
        return not self.is_production

    def check_security_config(self) -> list[str]:
        """返回 SECRET_KEY 的问题列表（空列表 = 通过）。只读，不抛异常。"""
        problems: list[str] = []
        secret = (self.SECRET_KEY or "").strip()
        if not secret:
            problems.append("SECRET_KEY 为空")
        elif secret in PLACEHOLDER_SECRET_KEYS:
            problems.append("SECRET_KEY 仍是仓库模板里的公开占位值")
        elif len(secret.encode("utf-8")) < MIN_SECRET_KEY_BYTES:
            problems.append(f"SECRET_KEY 太短（< {MIN_SECRET_KEY_BYTES} 字节，熵不足）")
        return problems

    def assert_secure_config(self) -> list[str]:
        """启动期安全自检：生产环境不安全就**拒绝启动**（fail-fast）。

        审计 §6.1-1：默认 SECRET_KEY 是公开值，按仓库现状部署任何人都能签发
        ROOT token。这里把它变成"起不来"，而不是"起来了但没人知道"。

        Returns:
            list[str]: 问题列表；生产环境有问题时抛 :class:`RuntimeError`，
            开发/测试环境返回问题列表交给调用方告警（本地开箱可用）。
        """
        problems = self.check_security_config()
        if not problems:
            return []
        if self.is_production:
            raise RuntimeError(
                "拒绝启动："
                + "；".join(problems)
                + "。请执行 `openssl rand -hex 32` 生成后写入 SECRET_KEY"
                "（环境变量或 .env.production），审计 §6.1。"
            )
        return problems

    def check_llm_config(self) -> list[str]:
        """校验 LLM Provider / 模型 / API Key 组合，返回警告信息列表。

        返回空列表表示配置自洽（Provider、模型名前缀、API Key 均匹配）。
        该方法只读取配置，不修改任何状态，可在启动时安全调用。

        Returns:
            list[str]: 人类可读的配置警告；空列表代表未发现明显问题。
        """
        issues: list[str] = []
        # 别名归一（历史 agens → agnes）：既避免旧配置被误报为"不受支持"，
        # 也让归一后的键与 PROVIDER_MODEL_PREFIXES 的取值空间严格一致。
        provider = normalize_provider(self.LLM_PROVIDER)
        model = (self.LLM_MODEL or "").strip()

        if provider not in LLM_PROVIDERS:
            issues.append(
                f"LLM_PROVIDER='{self.LLM_PROVIDER}' 不受支持，"
                f"可选值: {', '.join(LLM_PROVIDERS)}"
            )
            return issues

        if not model:
            issues.append("LLM_MODEL 为空，无法确定要调用的模型名")
            return issues

        # Provider 与模型名前缀匹配校验（例如 agnes 只能用 agnes-* 模型）
        expected_prefix = PROVIDER_MODEL_PREFIXES[provider]
        if not model.startswith(expected_prefix):
            issues.append(
                f"LLM_PROVIDER='{provider}' 与 LLM_MODEL='{model}' 不匹配："
                f"{provider} 的模型名应以 '{expected_prefix}' 开头"
            )
        elif model not in KNOWN_MODELS.get(provider, ()):
            issues.append(
                f"LLM_MODEL='{model}' 不在已知模型列表 {KNOWN_MODELS.get(provider)} 中，"
                f"请确认 Provider 侧确实提供该模型"
            )

        # API Key / Base URL 校验
        if provider == "agnes":
            if not (self.AGNES_API_KEY or "").strip():
                issues.append("AGNES_API_KEY 未配置，Agnes 接口调用将返回 401")
            if not (self.AGNES_API_BASE or "").strip():
                issues.append("AGNES_API_BASE 未配置，无法定位 Agnes 接口地址")
        elif provider == "deepseek":
            if not (self.DEEPSEEK_API_KEY or "").strip():
                issues.append("DEEPSEEK_API_KEY 未配置，DeepSeek 接口调用将返回 401")
            if not (self.DEEPSEEK_API_BASE or "").strip():
                issues.append("DEEPSEEK_API_BASE 未配置，无法定位 DeepSeek 接口地址")

        return issues


settings = Settings()


# ---- 根据 DATABASE_TYPE 构建最终 DATABASE_URL（若未手动指定） ----
if settings.DATABASE_TYPE == "postgresql":
    # 检查 DATABASE_URL 是否为默认 SQLite 值，若是则构造 PostgreSQL URL
    _default_sqlite = "sqlite+aiosqlite:///./knowledge.db"
    if settings.DATABASE_URL == _default_sqlite or settings.DATABASE_URL.startswith("sqlite"):
        settings.DATABASE_URL = (
            f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
            f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )
elif settings.DATABASE_TYPE == "sqlite":
    # SQLite：如果是相对路径（以 ./ 开头），保持原样，不做绝对路径转换。
    # 绝对路径（如 Windows 的 D:/xxx）会导致 SQLAlchemy URL 解析报错：
    # ValueError: too many values to unpack
    _db_url = settings.DATABASE_URL
    if _db_url.startswith("sqlite"):
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if _db_url.startswith(prefix):
                _db_path = _db_url[len(prefix):]
                # 仅当路径明确是绝对路径时才转换
                if _db_path and not _db_path.startswith(".") and not _db_path.startswith("/"):
                    settings.DATABASE_URL = prefix + _make_absolute(_db_path)
                # 否则保持原始相对路径（如 ./knowledge.db）
                break

# 标准化其他路径
settings.CHROMA_PERSIST_DIR = _make_absolute(settings.CHROMA_PERSIST_DIR)
settings.UPLOAD_DIR = _make_absolute(settings.UPLOAD_DIR)
settings.SPARSE_INDEX_PATH = _make_absolute(settings.SPARSE_INDEX_PATH)

# ---- DATABASE_URL 兼容性校验 ----
if settings.DATABASE_URL and "sqlite" in settings.DATABASE_URL:
    _url = settings.DATABASE_URL
    # 检查是否包含 Windows 驱动器号绝对路径（如 sqlite+aiosqlite:///D:\）
    if _url.startswith("sqlite"):
        for _prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if _url.startswith(_prefix):
                _path_part = _url[len(_prefix):]
                # 检测 Windows 反斜杠路径
                if "\\" in _path_part:
                    print(
                        "ERROR: Invalid DATABASE_URL format.\n"
                        f"Found Windows backslash path: {_url}\n\n"
                        "Please use forward slashes. Example:\n"
                        "  sqlite+aiosqlite:///./knowledge.db"
                    )
                    sys.exit(1)
                break

# 确保目录存在
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
