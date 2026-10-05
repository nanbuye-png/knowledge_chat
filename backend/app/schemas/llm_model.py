"""LLMModel CRUD API 的 Pydantic 模型。

Provider 取值在这里做「别名归一 + 白名单」校验：手工在「Model Registry」页面
填写的 provider 会先归一成规范键（历史写法 ``agens`` → ``agnes``）再落库，
不支持的取值直接 422 —— 避免脏数据在**运行期**才变成 Agent 的
「Agent 生成回答失败」。历史脏数据由 alembic 迁移 ``b7c1d5e9a3f2`` 修正，
运行期另有 :func:`app.core.config.normalize_provider` 兜底。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from ..core.config import LLM_PROVIDERS, normalize_provider

_PROVIDER_HINT = "（规范键即厂商品牌名 agnes；历史写法 agens 也会自动归一）"


def _normalize_and_check_provider(value: str) -> str:
    """归一 Provider 别名并拒绝不支持的取值（Create / Update 共用）。"""
    normalized = normalize_provider(value)
    if normalized not in LLM_PROVIDERS:
        raise ValueError(
            f"Provider '{value}' 不受支持，可选值: {', '.join(LLM_PROVIDERS)}"
            + _PROVIDER_HINT
        )
    return normalized


class LLMModelCreate(BaseModel):
    """创建新 LLM 模型配置的请求模型。"""
    name: str = Field(..., min_length=1, max_length=100, description="模型显示名称")
    provider: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Provider 类型: deepseek, agnes（历史写法 agens 自动归一为 agnes）",
    )
    model_name: str = Field(..., min_length=1, max_length=100, description="实际 API 调用模型标识")
    enabled: bool = Field(default=True, description="是否启用")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """归一别名 + 白名单校验，保证落库的 Provider 一定能被工厂识别。"""
        return _normalize_and_check_provider(v)


class LLMModelUpdate(BaseModel):
    """更新现有 LLM 模型配置的请求模型。所有字段均为可选。"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模型显示名称")
    provider: Optional[str] = Field(default=None, min_length=1, max_length=50, description="Provider 类型")
    model_name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="实际 API 调用模型标识")
    enabled: Optional[bool] = Field(default=None, description="是否启用")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: Optional[str]) -> Optional[str]:
        """部分更新允许缺省，但不允许把 Provider 改成不支持的取值。"""
        if v is None:
            return v
        return _normalize_and_check_provider(v)


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