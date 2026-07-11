"""PromptTemplateVersion model — immutable version history for prompt templates."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from .document import Base


class PromptTemplateVersion(Base):
    """Stores an immutable snapshot of a prompt template's content at a given version.

    Each time :class:`PromptTemplate` content is updated, a new version
    record is created.  Versions are never deleted — only appended.
    """

    __tablename__ = "prompt_template_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship back to the parent template (optional navigation)
    template = relationship("PromptTemplate", back_populates="versions")

    def __repr__(self) -> str:
        return (
            f"<PromptTemplateVersion(id={self.id}, template_id={self.template_id}, "
            f"version={self.version})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "template_id": self.template_id,
            "version": self.version,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }