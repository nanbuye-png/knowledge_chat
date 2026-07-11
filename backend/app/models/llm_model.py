"""LLM model configuration — stores available LLM provider/model entries."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from .document import Base


class LLMModel(Base):
    """Represents a configured LLM provider/model combination.

    This table stores which providers and models are available for use.
    It is the data foundation for multi-model support (Sprint 13.1).
    """

    __tablename__ = "llm_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="Display name for the model")
    provider = Column(String(50), nullable=False, comment="Provider type: deepseek, openai, gemini, etc.")
    model_name = Column(String(100), nullable=False, comment="Actual model identifier for API calls")
    enabled = Column(Boolean, nullable=False, default=True, comment="Whether this model is enabled")
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Record creation timestamp",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Last update timestamp",
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