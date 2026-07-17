""" add_token_blacklist_table

Revision ID: b08b874abe12
Revises: 568e4f6e381b
Create Date: 2026-07-16 23:35:17.689140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b08b874abe12'
down_revision: Union[str, Sequence[str], None] = '568e4f6e381b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "token_blacklist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="关联的用户 ID"),
        sa.Column("jti", sa.String(length=64), nullable=False, comment="JWT 唯一标识符（UUID）"),
        sa.Column("token_type", sa.String(length=20), nullable=False, server_default="access", comment="token 类型（access / refresh）"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="原始 token 过期时间"),
        sa.Column("revoked_at", sa.DateTime(), nullable=False, comment="撤销时间"),
        sa.Column("reason", sa.String(length=100), nullable=True, comment="撤销原因（logout / disable / admin_revoke）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="记录创建时间"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )
    op.create_index("ix_token_blacklist_user_id", "token_blacklist", ["user_id"])
    op.create_index("ix_token_blacklist_jti", "token_blacklist", ["jti"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_token_blacklist_jti", table_name="token_blacklist")
    op.drop_index("ix_token_blacklist_user_id", table_name="token_blacklist")
    op.drop_table("token_blacklist")
