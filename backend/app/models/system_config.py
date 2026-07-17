"""SystemConfig - 系统动态配置中心。"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship

from .document import Base


class SystemConfig(Base):
    """系统动态配置（替代 .env 中的运行时配置）。"""
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    type = Column(String(20), nullable=False, default="string")  # string, int, bool, json
    description = Column(String(500), nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))