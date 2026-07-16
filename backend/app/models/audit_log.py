from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import DeclarativeBase

from .document import Base


class AuditLog(Base):
    """管理员操作审计日志。"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(Integer, nullable=False, index=True, comment="操作者用户ID")
    action = Column(String(50), nullable=False, index=True, comment="操作类型，如 ENABLE_USER")
    target_type = Column(String(50), nullable=False, index=True, comment="目标对象类型，如 user")
    target_id = Column(Integer, nullable=True, index=True, comment="目标对象ID")
    detail = Column(Text, nullable=True, comment="变更详情 JSON")
    ip_address = Column(String(64), nullable=True, comment="操作者IP地址")
    user_agent = Column(String(255), nullable=True, comment="客户端 User-Agent")
    status = Column(String(20), nullable=False, default="SUCCESS", server_default="SUCCESS", comment="结果状态：SUCCESS / FAILURE")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "operator_id": self.operator_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "detail": self.detail,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
