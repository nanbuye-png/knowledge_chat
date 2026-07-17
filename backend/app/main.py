from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import os
import sys

# 将父目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .core.config import settings
from .core.logging import setup_logging
from .core.exceptions import AppError, app_error_handler, http_exception_handler
from .api.documents import router as documents_router
from .api.chat import router as chat_router
from .api.health import router as health_router
from .api.auth import router as auth_router
from .api.auth_sessions import router as auth_sessions_router
from .api.knowledge_bases import router as knowledge_bases_router
from .api.conversation import router as conversation_router
from .api.llm_model import router as llm_model_router
from .api.prompt_template import router as prompt_template_router
from .api.prompt_version import router as prompt_version_router
from .api.knowledge_config import router as knowledge_config_router
from .api.usage import router as usage_router
from .api.admin.users import router as admin_users_router
from .api.admin.dashboard import router as admin_dashboard_router
from .api.admin.audit_logs import router as admin_audit_logs_router
from .api.admin.sessions import router as admin_sessions_router
from .api.admin.organizations import router as admin_organizations_router
from .api.api_keys import router as api_keys_router
from .storage.database import init_db, close_db
from .storage.vector_store import vector_store
from .services.embedding_service import embedding_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器。"""
    # 启动
    setup_logging()
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 正在启动...")
    logger.info("=" * 60)

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
    logger.info(f"🔗 LLM Provider: {settings.LLM_PROVIDER}")
    
    # 动态显示当前 Provider 的 endpoint
    if settings.LLM_PROVIDER == "deepseek":
        logger.info(f"🔗 DeepSeek API: {settings.DEEPSEEK_API_BASE}")
    elif settings.LLM_PROVIDER == "agens":
        logger.info(f"🔗 Agens API: {settings.AGENS_API_BASE}")
    
    logger.info(f"🗄️  数据库: {settings.DATABASE_URL}")
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
    docs_url="/docs",
    redoc_url="/redoc",
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


# 全局异常处理器
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器：处理未捕获的错误。"""
    logger.error(f"Unhandled error: {exc} on {request.url}")
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
        },
    )


# 注册路由
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(auth_sessions_router)
app.include_router(knowledge_bases_router)
app.include_router(conversation_router)
app.include_router(llm_model_router)
app.include_router(prompt_template_router)
app.include_router(prompt_version_router)
app.include_router(knowledge_config_router)
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