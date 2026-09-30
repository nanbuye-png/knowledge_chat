"""add api_keys table (real DDL)

Revision ID: a1f4c7d92b36
Revises: d8f5b2c60a31
Create Date: 2026-09-30 18:00:00.000000

审计 §6.1-5：``d5660fbbb75e`` 是**空桩**（upgrade 里只有一个 ``pass``），
却已被 stamp 成迁移链上的一环 —— 于是全新部署跑完 ``alembic upgrade head``
仍然没有 ``api_keys`` 表（开发库实测 26 张表、无 api_keys），而
``/api/api-keys`` 一经调用就是 500。

根因是 ``alembic/env.py`` 手写模型导入清单，新增模型没被加进去，
autogenerate 于是产出了空迁移（本提交同时把 env.py 改成自动收集）。

这里补上真实 DDL，并与 ``app/models/api_key.py`` 的列定义逐一对齐
（``is_active`` 的 ``server_default="1"``、``key_hash`` 的 UNIQUE、
``user_id`` 的 ON DELETE CASCADE 都照模型来，避免模型与迁移漂移）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1f4c7d92b36'
down_revision: Union[str, Sequence[str], None] = 'd8f5b2c60a31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_api_keys_table() -> bool:
    """表是否已存在（幂等保护）。

    两种情况会碰到「表已经在了」：本地用回退模式 ``create_all`` 建过库，
    或历史环境手工补过表。此时迁移应当跳过而不是把启动卡死。
    """
    return sa.inspect(op.get_bind()).has_table("api_keys")


def upgrade() -> None:
    """Upgrade schema."""
    if _has_api_keys_table():
        return

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    # index=True（user_id）+ __table_args__ 里显式声明的 key_hash 索引
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])


def downgrade() -> None:
    """Downgrade schema."""
    # 直接 drop table：索引随表一起消失，SQLite/PostgreSQL 行为一致，
    # 不必再关心索引是否被历史环境改过名。
    if _has_api_keys_table():
        op.drop_table("api_keys")
