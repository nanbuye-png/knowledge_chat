"""Pydantic schemas for PromptTemplateVersion API."""
from pydantic import BaseModel


class PromptVersionResponse(BaseModel):
    """Schema for a single prompt template version."""
    id: int
    template_id: int
    version: int
    content: str
    created_at: str

    class Config:
        from_attributes = True