"""LLM 用量 — 每次 LLM 调用的追踪记录。"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from .document import Base


class LLMUsage(Base):
    """记录每次 LLM 调用，用于分析和计费。

    存储在 ``llm_usages`` 表中。token 计数为可选字段
    （当提供商不报告时填 0）。
    """

    __tablename__ = "llm_usages"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id"), nullable=True, index=True
    )

    provider = Column(String(50), nullable=False, comment="如 deepseek、agens")
    model = Column(String(100), nullable=False, comment="如 deepseek-chat")

    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)

    latency_ms = Column(Float, nullable=False, default=0.0, comment="LLM 调用延迟（毫秒）")

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }