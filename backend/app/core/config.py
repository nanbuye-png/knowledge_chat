import sys
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


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "智能知识库问答系统"
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"  # development | production | testing

    # LLM 提供商
    LLM_PROVIDER: str = "deepseek"  # deepseek 或 agens

    # DeepSeek 配置
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"

    # Agens 配置
    AGENS_API_KEY: str = ""
    AGENS_API_BASE: str = ""

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
    EMBEDDING_DIM: int = 768

    # 嵌入
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # 文件上传
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: set = {
        ".pdf", ".docx", ".md", ".txt", ".doc"
    }

    # 分块
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100

    # JWT 认证
    SECRET_KEY: str = "knowledge-chat-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24

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
