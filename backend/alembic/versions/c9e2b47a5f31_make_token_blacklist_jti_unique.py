"""make token_blacklist.jti index unique (model says unique)

Revision ID: c9e2b47a5f31
Revises: a1f4c7d92b36
Create Date: 2026-09-30 18:20:00.000000

这条迁移不是"顺手改"，而是被新引入的 ``alembic check`` 抓出来的**模型/迁移
漂移**（与 api_keys 空桩同一个根因：迁移没人对账）：

* 模型 ``app/models/token_blacklist.py``：``jti = Column(..., unique=True, index=True)``
  → 应当存在**唯一索引** ``ix_token_blacklist_jti``；
* ``b08b874abe12`` 建的是「表级 UNIQUE(jti) + 普通索引」，``alembic check``
  直接报 ``Detected changed index 'ix_token_blacklist_jti' ... unique=False to unique=True``。

jti 唯一性是"撤销 token"语义的前提（同名 jti 重复写入会让黑名单查重失效），
因此按模型对齐。表级 UNIQUE 约束保留（语义相同，删除它会带来更大的重建风险）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9e2b47a5f31'
down_revision: Union[str, Sequence[str], None] = 'a1f4c7d92b36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_token_blacklist_jti"
_TABLE_NAME = "token_blacklist"


def _index_is_unique() -> bool | None:
    """返回索引当前的 unique 标记；索引不存在时返回 None。"""
    for index in sa.inspect(op.get_bind()).get_indexes(_TABLE_NAME):
        if index.get("name") == _INDEX_NAME:
            return bool(index.get("unique"))
    return None


def upgrade() -> None:
    """Upgrade schema."""
    unique = _index_is_unique()
    if unique is None or unique:
        # 索引不存在（异常环境）或已经是唯一的：无事可做，保持迁移可重复执行。
        return
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
    op.create_index(_INDEX_NAME, _TABLE_NAME, ["jti"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    unique = _index_is_unique()
    if not unique:
        return
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
    op.create_index(_INDEX_NAME, _TABLE_NAME, ["jti"], unique=False)
