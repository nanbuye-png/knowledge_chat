""" merge_heads_session_and_rbac

Revision ID: 568e4f6e381b
Revises: 004eb1d924e4, 2a3b4c5d6e7f
Create Date: 2026-07-16 23:35:02.724857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '568e4f6e381b'
down_revision: Union[str, Sequence[str], None] = ('004eb1d924e4', '2a3b4c5d6e7f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
