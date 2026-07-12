"""LLM 模型配置 — 存储可用的 LLM 提供商/模型条目。"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from .document import Base


class LLMModel(Base):
    """表示已配置的 LLM 提供商/模型组合。

    此表存储哪些提供商和模型可供使用。
    是多模型支持的数据基础。
    """

    __tablename__ = "llm_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="模型的显示名称")
    provider = Column(String(50), nullable=False, comment="提供商类型：deepseek、openai、gemini 等")
    model_name = Column(String(100), nullable=False, comment="API 调用时使用的实际模型标识符")
    enabled = Column(Boolean, nullable=False, default=True, comment="是否启用此模型")
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="记录创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="最后更新时间",
    )

    def __repr__(self) -> str:
        return (
            f"<LLMModel(id={self.id}, name='{self.name}', "
            f"provider='{self.provider}', model_name='{self.model_name}', "
            f"enabled={self.enabled})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "model_name": self.model_name,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }