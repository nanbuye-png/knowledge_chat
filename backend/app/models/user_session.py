from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import DeclarativeBase

from .document import Base


class UserSession(Base):
    """用户登录 Session 记录。"""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="用户ID")
    token_hash = Column(String(128), nullable=False, index=True, comment="JWT token 的 SHA256 hash")
    device_info = Column(String(255), nullable=True, comment="设备信息")
    ip_address = Column(String(50), nullable=True, comment="登录IP")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    last_used_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), comment="最后使用时间")
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
            "is_active": self.revoked_at is None and self.expires_at > datetime.now(timezone.utc),
        }