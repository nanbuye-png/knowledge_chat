from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import os
import sys

# 将父目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .core.config import normalize_provider, settings
from .core.logging import setup_logging
from .core.exceptions import AppError, app_error_handler, http_exception_handler
from .api.documents import router as documents_router
from .api.chat import router as chat_router
from .api.knowledge_query import router as knowledge_query_router
from .api.health import router as health_router
from .api.auth import router as auth_router
from .api.auth_sessions import router as auth_sessions_router
from .api.knowledge_bases import router as knowledge_bases_router
from .api.conversation import router as conversation_router
from .api.llm_model import router as llm_model_router
from .api.agents import router as agents_router
from .api.workflows import router as workflows_router
from .api.prompt_template import router as prompt_template_router
from .api.prompt_version import router as prompt_version_router
from .api.knowledge_config import router as knowledge_config_router
from .api.tools import router as tools_router
from .api.usage import router as usage_router
from .api.admin.users import router as admin_users_router
from .api.admin.dashboard import router as admin_dashboard_router
from .api.admin.audit_logs import router as admin_audit_logs_router
from .api.admin.sessions import router as admin_sessions_router
from .api.admin.organizations import router as admin_organizations_router
from .api.api_keys import router as api_keys_router
from .services.metrics import router as metrics_router
from .storage.database import init_db, close_db
from .storage.vector_store import vector_store
from .services.embedding_service import embedding_service


def _mask_dsn(url: str) -> str:
    """脱敏数据库连接串（审计 §5.5：启动日志曾把 PostgreSQL 密码打出来）。"""
    if not url:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(url)
        if parts.password:
            netloc = f"{parts.username}:***@{parts.hostname}"
            if parts.port:
                netloc += f":{parts.port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))
    except Exception:  # pragma: no cover - 脱敏失败时退化为"不打印"
        return "<unparsable-dsn>"
    return url


def _api_docs_kwargs(cfg) -> dict:
    """按环境决定是否暴露 /docs、/redoc、/openapi.json（审计 §6.1-7）。

    生产环境默认全部关闭（``ENABLE_API_DOCS=true`` 可显式打开，仅用于受控
    调试）——接口文档等于把攻击面直接摊开给扫描器。开发环境保持可用，
    否则本地开发体验会明显变差。

    抽成函数而不是内联，是为了让"关掉了吗"能被单测直接断言，
    不必 reload 整个 ``app.main``（reload 会连带重建引擎，见 conftest 的说明）。
    """
    if cfg.docs_enabled:
        return {"docs_url": "/docs", "redoc_url": "/redoc"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器。"""
    # 1) 安全配置自检必须最先执行（审计 §6.1）：占位 SECRET_KEY 的生产环境
    #    直接拒绝启动，绝不"带病上线"；开发环境只告警。
    security_problems = settings.assert_secure_config()

    # 启动
    setup_logging()
    if security_problems:
        logger.warning(
            "⚠️  不安全的 SECRET_KEY（开发环境允许，禁止用于生产）："
            + "；".join(security_problems)
            + "。生产环境会拒绝启动。"
        )
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 正在启动...")
    logger.info("=" * 60)

    # 初始化基础设施 Provider（Cache / Worker）+ 启动自检（P0-1）
    try:
        from .services.factory import bootstrap_infrastructure

        infra = await bootstrap_infrastructure()
        logger.info(
            f"✅ 基础设施初始化: cache={infra.cache_type}({infra.cache_backend}), "
            f"worker={infra.worker_type}({infra.worker_backend}), "
            f"redis_reachable={infra.redis_reachable}"
        )
        if infra.details:
            logger.warning(f"⚠️  {infra.details}")
    except Exception as e:
        logger.warning(f"⚠️ 基础设施初始化失败: {e}")

    # 初始化数据库
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"⚠️ Database initialization issue: {e}")
        logger.info("Will continue without database...")

    # 初始化向量存储
    try:
        await vector_store.initialize()
        logger.info("✅ Vector store initialized")
    except Exception as e:
        logger.warning(f"⚠️ Vector store initialization issue: {e}")
        logger.info("Will continue without vector store...")

    # 初始化嵌入服务
    try:
        await embedding_service.initialize()
        logger.info("✅ Embedding service initialized")
    except Exception as e:
        logger.warning(f"⚠️ Embedding service initialization issue: {e}")
        logger.info("Will continue without embedding service...")

    # 启动摘要
    logger.info("=" * 60)
    logger.info(f"✅ {settings.APP_NAME} 启动完成")
    logger.info(f"📡 API 文档: http://localhost:8000/docs")
    logger.info(f"🔗 LLM Provider: {settings.LLM_PROVIDER} | 🤖 LLM 模型: {settings.LLM_MODEL}")
    
    # 动态显示当前 Provider 的 endpoint（别名归一：历史 agens → agnes）
    active_provider = normalize_provider(settings.LLM_PROVIDER)
    if active_provider == "deepseek":
        logger.info(f"🔗 DeepSeek API: {settings.DEEPSEEK_API_BASE}")
    elif active_provider == "agnes":
        logger.info(f"🔗 Agnes API: {settings.AGNES_API_BASE}")

    # LLM 配置自检（Provider / 模型 / API Key 是否匹配）
    for issue in settings.check_llm_config():
        logger.warning(f"⚠️  LLM 配置检查: {issue}")
    
    logger.info(f"🗄️  数据库: {_mask_dsn(settings.DATABASE_URL)}")
    logger.info(f"📦 向量存储: {settings.VECTOR_STORE_TYPE}")
    logger.info(f"🔤 嵌入模型: {settings.EMBEDDING_MODEL}")
    logger.info("=" * 60)

    yield

    # 关闭
    logger.info("🛑 正在关闭服务...")
    await close_db()
    await vector_store.close()
    await embedding_service.close()
    logger.info("✅ 服务已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="智能知识库问答系统 - 支持文档上传、RAG 问答、通用 AI 闲聊",
    lifespan=lifespan,
    # /docs、/redoc、/openapi.json：生产默认关闭（审计 §6.1-7）
    **_api_docs_kwargs(settings),
)

# 跨域中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 安全 Headers 中间件
from .middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# 限流中间件
from .middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# 请求级指标 + request_id 中间件（Phase 3 §5.6）
from .middleware.metrics import MetricsMiddleware
app.add_middleware(MetricsMiddleware)


# 全局异常处理器
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器：处理未捕获的错误。

    审计 §5.5：这里此前用 ``logger.error(f"...{exc}")``，**不打堆栈**，
    线上 500 因此无法定位。改为 ``logger.exception``（带 traceback），
    并在响应里带上 request_id，便于前端报障时对齐日志。
    """
    from .core.context import get_request_id

    request_id = getattr(request.state, "request_id", None) or get_request_id()
    logger.exception(f"Unhandled error on {request.url} (request_id={request_id})")
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
            "request_id": request_id,
        },
    )


# 注册路由
app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(auth_sessions_router)
app.include_router(knowledge_bases_router)
app.include_router(conversation_router)
app.include_router(knowledge_query_router)
app.include_router(llm_model_router)
app.include_router(prompt_template_router)
app.include_router(prompt_version_router)
app.include_router(knowledge_config_router)
app.include_router(tools_router)
app.include_router(agents_router)
app.include_router(workflows_router)
app.include_router(usage_router)
app.include_router(admin_users_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_audit_logs_router)
app.include_router(admin_sessions_router)
app.include_router(api_keys_router)
app.include_router(admin_organizations_router)


@app.get("/", tags=["根路径"])
async def root():
    """根路径 - API 信息。"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )