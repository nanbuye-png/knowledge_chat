"""企业组织核心模型。

Organization: 企业/组织
OrganizationMember: 用户与组织关联关系
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .document import Base


class Organization(Base):
    """企业组织。"""

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True, default=None)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关系
    members = relationship(
        "OrganizationMember",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Organization(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class OrganizationMember(Base):
    """用户组织成员关系。"""

    __tablename__ = "organization_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(20), nullable=False, default="MEMBER")  # OWNER, ADMIN, MEMBER
    joined_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    # 同一用户不能重复加入同一组织
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_org_member"
        ),
    )

    # 关系
    organization = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="organizations")

    def __repr__(self):
        return (
            f"<OrganizationMember(org_id={self.organization_id}, "
            f"user_id={self.user_id}, role='{self.role}')>"
        )