from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import os

# 计算项目 backend 目录（从此文件向上 3 级: core/config.py -> app -> backend）
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _make_absolute(path: str) -> str:
    """将相对路径转换为以 backend 目录为根的绝对路径。"""
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str(_BACKEND_DIR / p)


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "智能知识库问答系统"
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"

    # LLM 提供商
    LLM_PROVIDER: str = "deepseek"  # deepseek 或 agens

    # DeepSeek 配置
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"

    # Agens 配置
    AGENS_API_KEY: str = ""
    AGENS_API_BASE: str = ""

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./knowledge.db"

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
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()

# 标准化路径：将相对路径修复为以 backend 目录为根的绝对路径。
# 处理 DATABASE_URL（SQLite）、CHROMA_PERSIST_DIR 和 UPLOAD_DIR。
# DATABASE_URL 在 URL 中包含文件路径，因此需要仔细解析。
_db_url = settings.DATABASE_URL
if _db_url.startswith("sqlite"):
    # 提取 'sqlite+aiosqlite:///' 或 'sqlite:///' 之后的文件路径部分
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if _db_url.startswith(prefix):
            _db_path = _db_url[len(prefix):]
            settings.DATABASE_URL = prefix + _make_absolute(_db_path)
            break
settings.CHROMA_PERSIST_DIR = _make_absolute(settings.CHROMA_PERSIST_DIR)
settings.UPLOAD_DIR = _make_absolute(settings.UPLOAD_DIR)

# 确保目录存在
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
