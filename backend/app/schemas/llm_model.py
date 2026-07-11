"""Pydantic schemas for LLMModel CRUD API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LLMModelCreate(BaseModel):
    """Schema for creating a new LLM model configuration."""
    name: str = Field(..., min_length=1, max_length=100, description="模型显示名称")
    provider: str = Field(..., min_length=1, max_length=50, description="Provider 类型: deepseek, openai, gemini")
    model_name: str = Field(..., min_length=1, max_length=100, description="实际 API 调用模型标识")
    enabled: bool = Field(default=True, description="是否启用")


class LLMModelUpdate(BaseModel):
    """Schema for updating an existing LLM model configuration. All fields optional."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模型显示名称")
    provider: Optional[str] = Field(default=None, min_length=1, max_length=50, description="Provider 类型")
    model_name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="实际 API 调用模型标识")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


class LLMModelResponse(BaseModel):
    """Schema for LLM model response (read)."""
    id: int
    name: str
    provider: str
    model_name: str
    enabled: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True