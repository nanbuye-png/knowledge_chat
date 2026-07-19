"""add user system account flag

Revision ID: c6a5c6037e49
Revises: bf6115a6d8f7
Create Date: 2026-07-19 00:35:24.957209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6a5c6037e49'
down_revision: Union[str, Sequence[str], None] = 'bf6115a6d8f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 只添加 is_system_account 列，不修改其他表
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_system_account', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_system_account')