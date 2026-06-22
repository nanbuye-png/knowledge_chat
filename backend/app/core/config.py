from pydantic_settings import BaseSettings
from typing import Optional
import os


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

    # CORS
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000", "http://localhost"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.dirname(settings.CHROMA_PERSIST_DIR) if os.path.dirname(settings.CHROMA_PERSIST_DIR) else ".", exist_ok=True)