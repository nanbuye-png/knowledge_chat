"""PromptTemplate 模型 — 存储可复用的提示词模板配置。"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from .document import Base


class PromptTemplate(Base):
    """表示可复用的提示词模板。

    支持版本管理和为不同提示词类型（rag、chat、title 等）提供启用/禁用控制。
    """

    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    prompt_type = Column(String(50), nullable=False, comment="类型：rag、chat、title 等")
    content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True, comment="此模板版本当前是否处于激活状态")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 一对多关系：PromptTemplate 1 → N PromptTemplateVersion
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
            f"enabled={self.enabled}, is_active={self.is_active})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "prompt_type": self.prompt_type,
            "content": self.content,
            "version": self.version,
            "enabled": self.enabled,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
