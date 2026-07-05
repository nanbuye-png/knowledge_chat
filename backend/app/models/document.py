import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, BigInteger, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class DocumentStatus(str, enum.Enum):
    PROCESSING = "processing"
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
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

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
            "knowledge_base_id": self.knowledge_base_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
