"""Pydantic schemas for PromptTemplate CRUD API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PromptTemplateCreate(BaseModel):
    """Schema for creating a new prompt template."""
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    prompt_type: str = Field(..., min_length=1, max_length=50, description="类型: rag, chat, title 等")
    content: str = Field(..., min_length=1, description="模板内容")
    version: int = Field(default=1, ge=1, description="版本号")
    enabled: bool = Field(default=True, description="是否启用")


class PromptTemplateUpdate(BaseModel):
    """Schema for updating an existing prompt template. All fields optional."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模板名称")
    prompt_type: Optional[str] = Field(default=None, min_length=1, max_length=50, description="类型")
    content: Optional[str] = Field(default=None, min_length=1, description="模板内容")
    version: Optional[int] = Field(default=None, ge=1, description="版本号")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


class PromptTemplateResponse(BaseModel):
    """Schema for prompt template response (read)."""
    id: int
    name: str
    prompt_type: str
    content: str
    version: int
    enabled: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True