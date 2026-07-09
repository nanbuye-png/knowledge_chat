from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import os

# Compute the project backend directory (3 levels up from this file: core/config.py -> app -> backend)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _make_absolute(path: str) -> str:
    """Convert a relative path to an absolute path rooted at the backend directory."""
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str(_BACKEND_DIR / p)


class Settings(BaseSettings):
    # App
    APP_NAME: str = "智能知识库问答系统"
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./knowledge.db"

    # Vector Store
    VECTOR_STORE_TYPE: str = "chroma"  # chroma or qdrant
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    COLLECTION_NAME: str = "documents"
    EMBEDDING_DIM: int = 768

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # File upload
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: set = {
        ".pdf", ".docx", ".md", ".txt", ".doc"
    }

    # Chunking
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100

    # JWT Auth
    SECRET_KEY: str = "knowledge-chat-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24

    # CORS
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000", "http://localhost"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()

# Normalize paths: fix relative paths to be absolute, rooted at the backend directory.
# This handles DATABASE_URL (SQLite), CHROMA_PERSIST_DIR, and UPLOAD_DIR.
# DATABASE_URL contains a file path inside the URL, so we parse it carefully.
_db_url = settings.DATABASE_URL
if _db_url.startswith("sqlite"):
    # Extract the file path part after 'sqlite+aiosqlite:///' or 'sqlite:///'
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if _db_url.startswith(prefix):
            _db_path = _db_url[len(prefix):]
            settings.DATABASE_URL = prefix + _make_absolute(_db_path)
            break
settings.CHROMA_PERSIST_DIR = _make_absolute(settings.CHROMA_PERSIST_DIR)
settings.UPLOAD_DIR = _make_absolute(settings.UPLOAD_DIR)

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
