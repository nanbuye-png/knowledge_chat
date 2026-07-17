"""Quota & QuotaUsage - 企业资源限制模型。"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .document import Base


class Quota(Base):
    """企业配额限制。"""
    __tablename__ = "quotas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    max_documents = Column(Integer, nullable=False, default=100)
    max_storage_mb = Column(Integer, nullable=False, default=1024)       # MB
    max_tokens_daily = Column(BigInteger, nullable=False, default=100000)
    max_tokens_monthly = Column(BigInteger, nullable=False, default=3000000)
    max_requests_per_min = Column(Integer, nullable=False, default=60)
    max_api_keys = Column(Integer, nullable=False, default=5)
    max_members = Column(Integer, nullable=False, default=50)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", backref="quota")


class QuotaUsage(Base):
    """配额使用统计。"""
    __tablename__ = "quota_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    tokens_used = Column(BigInteger, nullable=False, default=0)
    requests_count = Column(Integer, nullable=False, default=0)
    documents_count = Column(Integer, nullable=False, default=0)
    storage_bytes = Column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("organization_id", "date", name="uq_quota_usage_date"),
    )

    organization = relationship("Organization", backref="quota_usage")