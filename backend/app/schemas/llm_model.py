"""LLMModel CRUD API 的 Pydantic 模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LLMModelCreate(BaseModel):
    """创建新 LLM 模型配置的请求模型。"""
    name: str = Field(..., min_length=1, max_length=100, description="模型显示名称")
    provider: str = Field(..., min_length=1, max_length=50, description="Provider 类型: deepseek, openai, gemini")
    model_name: str = Field(..., min_length=1, max_length=100, description="实际 API 调用模型标识")
    enabled: bool = Field(default=True, description="是否启用")


class LLMModelUpdate(BaseModel):
    """更新现有 LLM 模型配置的请求模型。所有字段均为可选。"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模型显示名称")
    provider: Optional[str] = Field(default=None, min_length=1, max_length=50, description="Provider 类型")
    model_name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="实际 API 调用模型标识")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


class LLMModelResponse(BaseModel):
    """LLM 模型查询的响应模型。"""
    id: int
    name: str
    provider: str
    model_name: str
    enabled: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True