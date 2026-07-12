"""KnowledgeConfig CRUD 的 Pydantic 模型。"""

from typing import Optional

from pydantic import BaseModel, Field


class KnowledgeConfigCreate(BaseModel):
    """创建 KnowledgeBase 配置的请求模型。"""

    knowledge_base_id: int = Field(..., description="KnowledgeBase ID")
    chunk_size: Optional[int] = Field(
        default=None, ge=50, le=5000, description="分块大小（字符数）"
    )
    chunk_overlap: Optional[int] = Field(
        default=None, ge=0, le=1000, description="分块重叠（字符数）"
    )
    embedding_provider: Optional[str] = Field(
        default=None, max_length=50, description="嵌入提供者类型"
    )
    embedding_model: Optional[str] = Field(
        default=None, max_length=200, description="嵌入模型标识符"
    )
    retrieval_top_k: Optional[int] = Field(
        default=None, ge=1, le=100, description="检索 Top‑K 值"
    )


class KnowledgeConfigUpdate(BaseModel):
    """更新 KnowledgeBase 配置的请求模型。所有字段均为可选。"""

    chunk_size: Optional[int] = Field(
        default=None, ge=50, le=5000, description="Chunk size in characters"
    )
    chunk_overlap: Optional[int] = Field(
        default=None, ge=0, le=1000, description="Chunk overlap in characters"
    )
    embedding_provider: Optional[str] = Field(
        default=None, max_length=50, description="Embedding provider type"
    )
    embedding_model: Optional[str] = Field(
        default=None, max_length=200, description="Embedding model identifier"
    )
    retrieval_top_k: Optional[int] = Field(
        default=None, ge=1, le=100, description="Top‑K for retrieval"
    )


class KnowledgeConfigResponse(BaseModel):
    """KnowledgeConfig API 的响应模型。"""

    id: int
    knowledge_base_id: int
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    retrieval_top_k: Optional[int] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True