"""Token Blacklist 模型 — JWT token 撤销记录。

通过 JWT payload 中的 jti（JWT ID）追踪被撤销的 token，
与 UserSession（token hash）互补，提供更轻量的撤销查询。
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index

from .document import Base


class TokenBlacklist(Base):
    """JWT Token 黑名单。

    当用户主动注销或管理员吊销 token 时，将 jti 记录到此表。
    后续 JWT 验证流程会先查询此表，若 jti 存在则判定 token 已失效。
    """

    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的用户 ID",
    )
    jti = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="JWT 唯一标识符（UUID）",
    )
    token_type = Column(
        String(20),
        nullable=False,
        default="access",
        server_default="access",
        comment="token 类型（access / refresh）",
    )
    expires_at = Column(
        DateTime,
        nullable=False,
        comment="原始 token 过期时间",
    )
    revoked_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="撤销时间",
    )
    reason = Column(
        String(100),
        nullable=True,
        comment="撤销原因（logout / disable / admin_revoke）",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="记录创建时间",
    )

    __table_args__ = (
        Index("ix_token_blacklist_user_id", "user_id"),
        Index("ix_token_blacklist_jti", "jti"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "jti": self.jti,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }