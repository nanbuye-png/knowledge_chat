"""Knowledge ACL - 知识库企业权限控制模型。"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .document import Base


class KnowledgeACL(Base):
    """知识库访问控制。"""
    __tablename__ = "knowledge_acls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    permission = Column(String(20), nullable=False, default="READ")  # READ, WRITE, ADMIN
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    knowledge_base = relationship("KnowledgeBase", backref="acls")
    organization = relationship("Organization", backref="knowledge_acls")