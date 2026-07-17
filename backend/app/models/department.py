"""Department & Group 企业组织树模型。"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship

from .document import Base


class Department(Base):
    """部门 — 支持无限级部门树。"""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # 关系
    organization = relationship("Organization", backref="departments")
    parent = relationship("Department", remote_side=[id], backref="children")


class Group(Base):
    """用户组。"""
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", backref="groups")
    department = relationship("Department", backref="groups")