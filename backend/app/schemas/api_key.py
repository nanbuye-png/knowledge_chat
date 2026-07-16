"""API Key 相关 Pydantic Schema。"""

from datetime import datetime
from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    """创建 API Key 请求。"""
    name: str = Field(..., min_length=1, max_length=100, description="Key 名称")


class ApiKeyResponse(BaseModel):
    """API Key 响应（不包含明文 Key）。"""
    id: int
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: str | None = None
    expires_at: str | None = None
    created_at: str | None = None


class ApiKeyCreatedResponse(BaseModel):
    """API Key 创建成功响应（包含唯一一次的明文 Key）。"""
    id: int
    name: str
    api_key: str
    created_at: str | None = None


class ApiKeyRevokeResponse(BaseModel):
    """API Key 撤销响应。"""
    id: int
    name: str
    is_active: bool
    message: str