from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship

from .document import Base
from .permission import user_roles
from ..core.rbac import UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default=UserRole.USER, server_default=UserRole.USER)
    is_system_account = Column(Boolean, nullable=False, default=False, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    last_activity_at = Column(DateTime, nullable=True, default=None)
    last_login_at = Column(DateTime, nullable=True, default=None)
    failed_login_count = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(DateTime, nullable=True, default=None)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # RBAC 关系
    roles = relationship("Role", secondary=user_roles, back_populates="users")

    knowledge_bases = relationship(
        "KnowledgeBase",
        back_populates="user"
    )

    conversations = relationship(
        "Conversation",
        back_populates="user"
    )

    # 组织关系
    organizations = relationship(
        "OrganizationMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_system_flag: bool = False):
        """转换为字典。
        
        Args:
            include_system_flag: 是否包含系统账号标识（仅 ROOT 可见）
        """
        result = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "failed_login_count": self.failed_login_count,
            "locked_until": self.locked_until.isoformat() if self.locked_until else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_system_flag:
            result["is_system_account"] = self.is_system_account
        return result
