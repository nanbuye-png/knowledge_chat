"""PromptTemplate model — stores reusable prompt template configurations."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from .document import Base


class PromptTemplate(Base):
    """Represents a reusable prompt template.

    Supports versioning and enable/disable control for different prompt types
    (rag, chat, title, etc.).
    """

    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    prompt_type = Column(String(50), nullable=False, comment="Type: rag, chat, title, etc.")
    content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # One-to-many relationship: PromptTemplate 1 → N PromptTemplateVersion
    versions = relationship(
        "PromptTemplateVersion",
        back_populates="template",
        order_by="PromptTemplateVersion.version",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<PromptTemplate(id={self.id}, name='{self.name}', "
            f"prompt_type='{self.prompt_type}', version={self.version}, "
            f"enabled={self.enabled})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "prompt_type": self.prompt_type,
            "content": self.content,
            "version": self.version,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
