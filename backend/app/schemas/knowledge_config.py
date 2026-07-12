"""Pydantic schemas for KnowledgeConfig CRUD."""

from typing import Optional

from pydantic import BaseModel, Field


class KnowledgeConfigCreate(BaseModel):
    """Schema for creating a KnowledgeBase configuration."""

    knowledge_base_id: int = Field(..., description="KnowledgeBase ID")
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


class KnowledgeConfigUpdate(BaseModel):
    """Schema for updating a KnowledgeBase configuration. All fields optional."""

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
    """Schema for KnowledgeConfig API response."""

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