from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_size: int
    file_type: str
    status: str
    chunk_count: int = 0
    error_message: Optional[str] = None
    # Phase 3 §5.2：文档级重试次数（0 表示一次成功/未重试）
    retry_count: int = 0
    knowledge_base_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class UploadResponse(BaseModel):
    message: str
    document_id: str
    filename: str
    status: str = "processing"
    # Phase 3 §5.3 幂等：True 表示该知识库内已存在相同内容，本次未新建记录、
    # 也未派发新的处理任务；duplicated_of 指向被复用的文档 ID。
    skipped: bool = False
    duplicated_of: Optional[str] = None


class DeleteResponse(BaseModel):
    message: str
    document_id: str