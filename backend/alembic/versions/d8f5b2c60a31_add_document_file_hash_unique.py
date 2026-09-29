"""add_document_file_hash_unique

Phase 3 §5.3 幂等：``documents.file_hash``（SHA-256）+ 同知识库唯一约束。

* ``file_hash`` 允许 NULL：历史数据不回填，且唯一索引在 SQLite 与
  PostgreSQL 上都允许多个 NULL，因此本迁移**无需数据回填**。
* ``uq_documents_kb_file_hash`` 是幂等的最终防线：并发上传同一文件时
  由数据库层拒绝第二条重复记录（应用层"先查后写"覆盖不到这个窗口）。

Revision ID: d8f5b2c60a31
Revises: c3a7e41d9b52
Create Date: 2026-09-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f5b2c60a31'
down_revision: Union[str, Sequence[str], None] = 'c3a7e41d9b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('file_hash', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_documents_file_hash', ['file_hash'], unique=False)
        batch_op.create_unique_constraint(
            'uq_documents_kb_file_hash', ['knowledge_base_id', 'file_hash']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_constraint('uq_documents_kb_file_hash', type_='unique')
        batch_op.drop_index('ix_documents_file_hash')
        batch_op.drop_column('file_hash')
