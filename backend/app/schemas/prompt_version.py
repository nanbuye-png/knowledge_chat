"""PromptTemplateVersion API 的 Pydantic 模型。"""
from pydantic import BaseModel


class PromptVersionResponse(BaseModel):
    """单个提示词模板版本的响应模型。"""
    id: int
    template_id: int
    version: int
    content: str
    created_at: str

    class Config:
        from_attributes = True