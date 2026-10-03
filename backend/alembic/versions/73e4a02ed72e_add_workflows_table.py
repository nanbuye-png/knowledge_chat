"""add workflows table

Revision ID: 73e4a02ed72e
Revises: 9015d1a85a71
Create Date: 2026-10-03 17:42:10.585081

审计 §4（Agent / Workflow / Tools）的落地点：``workflows`` 表是 Workflow 的
**真实持久化**，替代此前"前端 Planned 占位页 + 后端没有模型/路由/服务"的状态。

本迁移由 ``alembic revision --autogenerate`` 生成（env.py 已改为自动收集
``app/models/*.py``），因此与 ``app/models/workflow.py`` 的列定义逐列一致 ——
``tests/test_api_keys_migration.py::test_alembic_check_reports_no_drift`` 会守住
"模型改了、迁移没跟上"的漂移。

autogenerate 当时还检测到 ``token_blacklist`` 的既有漂移（``id`` 的 NOT NULL /
``user_id`` 外键），那是**本仓库既有的历史差异**、与 Workflow 无关，且在新库上
执行 ``drop_constraint(None, ...)`` 会直接报错；因此这里**刻意删掉**那几条，
只保留 ``workflows`` 建表（既有漂移留给专门的迁移处理）。

与 ``9015d1a85a71``（agents）同样的幂等保护：本地若走过 ``create_all`` 兜底
建表（开发模式），迁移应当跳过而不是把启动卡死。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73e4a02ed72e'
down_revision: Union[str, Sequence[str], None] = '9015d1a85a71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_workflows_table() -> bool:
    """表是否已存在（幂等保护；create_all 兜底建库时不重复建表）。"""
    return sa.inspect(op.get_bind()).has_table("workflows")


def upgrade() -> None:
    """Upgrade schema."""
    if _has_workflows_table():
        return
    op.create_table('workflows',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='所属用户 ID（归属校验的唯一依据）'),
    sa.Column('name', sa.String(length=100), nullable=False, comment='Workflow 名称'),
    sa.Column('description', sa.Text(), nullable=True, comment='用途说明'),
    sa.Column('steps', sa.JSON(), nullable=False, comment='有序步骤清单（tool / arguments / when / on_error），见模块 docstring'),
    sa.Column('enabled', sa.Boolean(), server_default='1', nullable=False, comment='是否启用；禁用后执行返回 409'),
    sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=False, comment='最后更新时间'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('workflows', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflows_user_id'), ['user_id'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    if not _has_workflows_table():
        return
    with op.batch_alter_table('workflows', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workflows_user_id'))

    op.drop_table('workflows')

