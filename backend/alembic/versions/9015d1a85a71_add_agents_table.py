"""add agents table

Revision ID: 9015d1a85a71
Revises: c9e2b47a5f31
Create Date: 2026-09-30 20:11:15.905121

审计 §4（Agent / Workflow / Tools）的落地点：``agents`` 表是 Agent 的**真实
持久化**，替代此前"前端硬编码假数据 + 后端没有模型/路由"的状态。

本迁移由 ``alembic revision --autogenerate`` 生成（env.py 已改为自动收集
``app/models/*.py``），因此与 ``app/models/agent.py`` 的列定义逐列一致 ——
``tests/test_api_keys_migration.py::test_alembic_check_reports_no_drift`` 会守住
"模型改了、迁移没跟上"的漂移。

与 ``a1f4c7d92b36``（api_keys）同样的幂等保护：本地若走过 ``create_all`` 兜底
建表（开发模式），迁移应当跳过而不是把启动卡死。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9015d1a85a71'
down_revision: Union[str, Sequence[str], None] = 'c9e2b47a5f31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_agents_table() -> bool:
    """表是否已存在（幂等保护；create_all 兜底建库时不重复建表）。"""
    return sa.inspect(op.get_bind()).has_table("agents")


def upgrade() -> None:
    """Upgrade schema."""
    if _has_agents_table():
        return
    op.create_table('agents',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False, comment='所属用户 ID（归属校验的唯一依据）'),
    sa.Column('name', sa.String(length=100), nullable=False, comment='Agent 名称'),
    sa.Column('description', sa.Text(), nullable=True, comment='用途说明'),
    sa.Column('system_prompt', sa.Text(), nullable=True, comment='系统提示词（LLM 模式下作为 system message）'),
    sa.Column('knowledge_base_id', sa.Integer(), nullable=True, comment='绑定知识库；kb_search 会按它做归属校验'),
    sa.Column('model_id', sa.Integer(), nullable=True, comment='绑定 LLM 模型；为空则只做工具结果汇总（answer_mode=tools_only）'),
    sa.Column('tools', sa.JSON(), nullable=False, comment='允许使用的工具名列表（只能是注册表里真实存在的工具）'),
    sa.Column('max_tool_calls', sa.Integer(), server_default='3', nullable=False, comment='单次执行最多调用工具的次数（执行期还会被 TOOL_MAX_CALLS_PER_REQUEST 收紧）'),
    sa.Column('enabled', sa.Boolean(), server_default='1', nullable=False, comment='是否启用；禁用后执行返回 409'),
    sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=False, comment='最后更新时间'),
    sa.ForeignKeyConstraint(['knowledge_base_id'], ['knowledge_bases.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['model_id'], ['llm_models.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agents_knowledge_base_id'), ['knowledge_base_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agents_model_id'), ['model_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agents_user_id'), ['user_id'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    if not _has_agents_table():
        return
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agents_user_id'))
        batch_op.drop_index(batch_op.f('ix_agents_model_id'))
        batch_op.drop_index(batch_op.f('ix_agents_knowledge_base_id'))

    op.drop_table('agents')
