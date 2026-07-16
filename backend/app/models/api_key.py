"""API Key 模型 — 用于程序化 API 访问的密钥管理。

支持用户创建多个命名 API Key，用于程序化访问 Chat API。
密钥仅在创建时返回一次，数据库仅存储 SHA256 hash。
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index

from .document import Base


class ApiKey(Base):
    """用户 API Key。

    与 JWT Token 不同，API Key 用于程序化、长时间运行的 API 调用，
    可通过管理界面创建和撤销。
    """

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )
    name = Column(String(100), nullable=False, comment="Key 名称，如 Production API")
    key_hash = Column(String(128), nullable=False, unique=True, comment="SHA256(key)")
    key_prefix = Column(
        String(20),
        nullable=False,
        comment="Key 前缀，如 sk-kc-abcd，用于展示",
    )
    last_used_at = Column(DateTime, nullable=True, default=None, comment="最后使用时间")
    expires_at = Column(DateTime, nullable=True, default=None, comment="过期时间，NULL 表示永不过期")
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        comment="是否可用",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间",
    )

    __table_args__ = (
        Index("ix_api_keys_user_id", "user_id"),
        Index("ix_api_keys_key_hash", "key_hash"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }