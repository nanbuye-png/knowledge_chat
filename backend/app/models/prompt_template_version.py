"""PromptTemplateVersion 模型 — 提示词模板的不可变版本历史。"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from .document import Base


class PromptTemplateVersion(Base):
    """存储提示词模板在某个版本下的不可变内容快照。

    每次 :class:`PromptTemplate` 内容更新时，都会创建一条新的版本记录。
    版本永远不会被删除 — 只会追加。
    """

    __tablename__ = "prompt_template_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False, comment="此特定版本是否为当前激活版本")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 与父模板的反向关系（可选的导航属性）
    template = relationship("PromptTemplate", back_populates="versions")

    def __repr__(self) -> str:
        return (
            f"<PromptTemplateVersion(id={self.id}, template_id={self.template_id}, "
            f"version={self.version}, is_active={self.is_active})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "template_id": self.template_id,
            "version": self.version,
            "content": self.content,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
