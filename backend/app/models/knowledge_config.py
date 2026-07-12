"""KnowledgeConfig — 每个知识库的 AI 参数配置。"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .document import Base


class KnowledgeConfig(Base):
    """每个知识库可选的 AI 参数覆盖。

    当某 *knowledge_base_id* 存在记录时，Pipeline 将使用这些值
    替代全局 ``settings.*`` 默认值。

    与 :class:`KnowledgeBase` 为一对一关系。
    """

    __tablename__ = "knowledge_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    knowledge_base_id = Column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="父知识库",
    )

    # 分块
    chunk_size = Column(Integer, nullable=True, comment="覆盖 settings.CHUNK_SIZE")
    chunk_overlap = Column(
        Integer, nullable=True, comment="覆盖 settings.CHUNK_OVERLAP"
    )

    # 嵌入
    embedding_provider = Column(
        String(50), nullable=True, comment="如 'openai'、'local'"
    )
    embedding_model = Column(
        String(200),
        nullable=True,
        comment="覆盖 settings.EMBEDDING_MODEL",
    )

    # 检索
    retrieval_top_k = Column(
        Integer, nullable=True, comment="覆盖检索的默认 top_k 值"
    )

    # 时间戳
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

    # 关系
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