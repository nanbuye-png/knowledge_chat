from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import DeclarativeBase

from ..core.timeutil import as_naive_utc, utcnow
from .document import Base


class UserSession(Base):
    """用户登录 Session 记录。"""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="用户ID")
    token_hash = Column(String(128), nullable=False, index=True, comment="JWT token 的 SHA256 hash")
    device_info = Column(String(255), nullable=True, comment="设备信息")
    ip_address = Column(String(50), nullable=True, comment="登录IP")
    # 审计 §6.1-4：默认值也写 naive UTC（否则 SQLite 静默丢 tzinfo、
    # PostgreSQL 按会话时区转换），用 timeutil.utcnow 统一口径。
    created_at = Column(DateTime, nullable=False, default=utcnow, comment="创建时间")
    last_used_at = Column(DateTime, nullable=False, default=utcnow, comment="最后使用时间")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    revoked_at = Column(DateTime, nullable=True, index=True, comment="注销时间，NULL 表示未注销")

    # 注意：user_id / token_hash / revoked_at 的索引已由上面的 index=True 生成。
    # 这里原先还重复声明了同名 Index(...)，导致 Base.metadata.create_all()
    # 抛 "index ix_user_sessions_user_id already exists"（SQLite），
    # 使 storage/database.py 的建表回退路径静默失效。已删除重复声明。

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_info": self.device_info,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            # 审计 §6.1-4：库内 expires_at 是 naive，必须归一后再与 naive now 比
            "is_active": self.revoked_at is None and as_naive_utc(self.expires_at) > utcnow(),
        }