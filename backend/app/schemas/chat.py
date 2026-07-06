from pydantic import BaseModel, Field
from typing import Optional, Any


class ChatMode(BaseModel):
    mode: str = Field(..., pattern="^(knowledge|chat)$")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    knowledge_base_id: int = Field(..., description="知识库 ID（用于向量检索隔离）")
    conversation_id: Optional[int] = Field(default=None, description="会话 ID（可选，提供时保存用户消息）")


class SourceReference(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    text: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceReference] = []
    has_knowledge: bool = True


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    history: list[dict] = []


class ChatResponse(BaseModel):
    answer: str


class ErrorResponse(BaseModel):
    error: dict = Field(default_factory=lambda: {"code": "UNKNOWN", "message": "未知错误"})


class ModeResponse(BaseModel):
    mode: str


class CreateConversationRequest(BaseModel):
    knowledge_base_id: int = Field(..., description="知识库 ID")


class CreateConversationResponse(BaseModel):
    id: int
    title: str
    knowledge_base_id: int
    created_at: str


class ConversationListItem(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str