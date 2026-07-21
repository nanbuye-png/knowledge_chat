"""make_conversation_kb_id_nullable

Revision ID: 27dcc65b4cd0
Revises: c6a5c6037e49
Create Date: 2026-07-22 00:24:54.278172

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27dcc65b4cd0'
down_revision: Union[str, Sequence[str], None] = 'c6a5c6037e49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: make conversations.knowledge_base_id nullable."""
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.alter_column('knowledge_base_id',
               existing_type=sa.INTEGER(),
               nullable=True)


def downgrade() -> None:
    """Downgrade schema: revert conversations.knowledge_base_id to NOT NULL."""
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.alter_column('knowledge_base_id',
               existing_type=sa.INTEGER(),
               nullable=False)