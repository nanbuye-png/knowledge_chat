"""normalize llm_models.provider aliases (historical spelling -> agnes)

修订说明
--------
``llm_models.provider`` 允许在「Model Registry」（``/ai/models``）手工填写，
历史数据里出现过两种拼写：

* 厂商品牌名 ``agnes`` —— 与模型 ID（``agnes-2.5-flash``）、Base URL
  （``apihub.agnes-ai.com``）一致，**即现在的规范键**；
* 代码早期写的 ``agens`` —— 字母顺序写反。

两者只差一个字母顺序，早期版本下 ``LLMProviderFactory.create_from_model()`` 会
抛 ``Unknown LLM provider``，Agent / 工作流对外统一显示「Agent 生成回答失败」，
排查成本极高（真实事故）。现在代码侧规范键统一为 ``agnes``（历史 ``agens`` 仍作为
别名被接受），本迁移负责把**库内历史值**一次性收敛。

代码侧别名解析见 ``app/core/config.py::normalize_provider`` /
``PROVIDER_ALIASES``，写入口校验见 ``app/schemas/llm_model.py``：迁移清历史账，
别名 + 校验防回归。

Revision ID: f1a7b3c2d9e4
Revises: 73e4a02ed72e
Create Date: 2026-10-03
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1a7b3c2d9e4"
down_revision = "73e4a02ed72e"
branch_labels = None
depends_on = None


# 别名 → 规范键（与 ``app/core/config.py::PROVIDER_ALIASES`` 保持一致，
# 差异只在这里做 SQL 层的大小写/空白归一）
_ALIAS_TO_CANONICAL: dict[str, str] = {
    "agens": "agnes",
    "agness": "agnes",
    "agnes-ai": "agnes",
    "agnesai": "agnes",
    "deep-seek": "deepseek",
    "deepseek-ai": "deepseek",
}


def upgrade() -> None:
    """把历史脏数据收敛到规范键（对 SQLite / PostgreSQL 都可用）。"""
    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        op.execute(
            "UPDATE llm_models SET provider = '{canonical}' "
            "WHERE lower(trim(provider)) = '{alias}'".format(
                canonical=canonical, alias=alias
            )
        )


def downgrade() -> None:
    """不可逆：历史拼写已在 upgrade 里归一到规范键，刻意不做反向改写。

    回滚本迁移不会破坏任何数据 —— 代码侧的别名解析（``normalize_provider``）
    本来就能识别历史拼写 ``agens``。
    """
    pass
