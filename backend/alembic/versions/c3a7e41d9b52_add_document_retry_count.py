"""add_document_retry_count

Phase 3 §5.2 Retry：``documents.retry_count`` 记录文档级重试次数。

* ``server_default='0'`` + ``nullable=False``：既有行自动补 0，
  不需要数据回填（审计 P0 的迁移约定：可重复、可回滚、不丢数据）。
* 使用 ``batch_alter_table``：SQLite 需要表重建，PostgreSQL 走 ALTER TABLE。

Revision ID: c3a7e41d9b52
Revises: 27dcc65b4cd0
Create Date: 2026-09-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a7e41d9b52'
down_revision: Union[str, Sequence[str], None] = '27dcc65b4cd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'retry_count',
                sa.Integer(),
                nullable=False,
                server_default='0',
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_column('retry_count')
