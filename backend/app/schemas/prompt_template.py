"""PromptTemplate CRUD API 的 Pydantic 模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PromptTemplateCreate(BaseModel):
    """创建新提示词模板的请求模型。"""
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    prompt_type: str = Field(..., min_length=1, max_length=50, description="类型: rag, chat, title 等")
    content: str = Field(..., min_length=1, description="模板内容")
    version: int = Field(default=1, ge=1, description="版本号")
    enabled: bool = Field(default=True, description="是否启用")
    is_active: bool = Field(default=True, description="是否激活")


class PromptTemplateUpdate(BaseModel):
    """更新现有提示词模板的请求模型。所有字段均为可选。"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模板名称")
    prompt_type: Optional[str] = Field(default=None, min_length=1, max_length=50, description="类型")
    content: Optional[str] = Field(default=None, min_length=1, description="模板内容")
    version: Optional[int] = Field(default=None, ge=1, description="版本号")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    is_active: Optional[bool] = Field(default=None, description="是否激活")


class PromptTemplateResponse(BaseModel):
    """提示词模板查询的响应模型。"""
    id: int
    name: str
    prompt_type: str
    content: str
    version: int
    enabled: bool
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
