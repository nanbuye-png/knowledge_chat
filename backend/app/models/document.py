import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    BigInteger,
    ForeignKey,
    UniqueConstraint,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"        # 已落盘，等待后台处理
    PROCESSING = "processing"  # 后台处理中（解析/切分/向量化）
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False, index=True)
    file_size = Column(BigInteger, nullable=False, default=0)
    file_type = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default=DocumentStatus.PROCESSING.value, index=True)
    chunk_count = Column(Integer, nullable=False, default=0)
    error_message = Column(String(1000), nullable=True)
    # 文档级重试计数（Phase 3 §5.2）：记录这篇文档重试过几次，便于排障与前端展示
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    # 内容指纹（Phase 3 §5.3）：同一知识库内相同文件内容不再重复入库。
    # 可为 NULL —— 历史数据不回填，且 SQLite/PostgreSQL 的唯一索引都允许多个 NULL。
    file_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # 幂等的最终防线：并发上传同一文件时，数据库层直接拒绝第二条重复记录
        # （应用层的「先查后写」无法覆盖竞态窗口）。
        UniqueConstraint(
            "knowledge_base_id", "file_hash", name="uq_documents_kb_file_hash"
        ),
    )

    knowledge_base = relationship("KnowledgeBase", backref="documents")

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "error_message": self.error_message,
            "retry_count": self.retry_count or 0,
            "knowledge_base_id": self.knowledge_base_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
