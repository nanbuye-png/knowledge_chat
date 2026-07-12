"""KnowledgeConfig — per‑KnowledgeBase AI configuration."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .document import Base


class KnowledgeConfig(Base):
    """Optional per‑KB overrides for AI parameters.

    When a row exists for a *knowledge_base_id*, the pipeline uses these
    values instead of the global ``settings.*`` defaults.

    One‑to‑one with :class:`KnowledgeBase`.
    """

    __tablename__ = "knowledge_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    knowledge_base_id = Column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="Parent KnowledgeBase",
    )

    # Chunking
    chunk_size = Column(Integer, nullable=True, comment="Override settings.CHUNK_SIZE")
    chunk_overlap = Column(
        Integer, nullable=True, comment="Override settings.CHUNK_OVERLAP"
    )

    # Embedding
    embedding_provider = Column(
        String(50), nullable=True, comment="e.g. 'openai', 'local'"
    )
    embedding_model = Column(
        String(200),
        nullable=True,
        comment="Override settings.EMBEDDING_MODEL",
    )

    # Retrieval
    retrieval_top_k = Column(
        Integer, nullable=True, comment="Override default top_k for retrieval"
    )

    # Timestamps
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    knowledge_base = relationship("KnowledgeBase", backref="config", uselist=False)

    def __repr__(self) -> str:
        return (
            f"<KnowledgeConfig(id={self.id}, kb_id={self.knowledge_base_id}, "
            f"chunk_size={self.chunk_size}, embedding_model='{self.embedding_model}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "knowledge_base_id": self.knowledge_base_id,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "retrieval_top_k": self.retrieval_top_k,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }