"""normalize llm_models.provider -> agnes (history: agens -> agnes)

修订说明
--------
上一版迁移 ``f1a7b3c2d9e4`` 把 ``llm_models.provider`` 从厂商品牌名 ``agnes``
收敛到当时代码里的键 ``agens``。但 ``agens`` 本身就是字母顺序写反的拼写：

* 厂商品牌名、模型 ID（``agnes-2.5-flash``）与 Base URL（``apihub.agnes-ai.com``）
  都是 ``agnes``；
* ``agens`` 只存在于代码/数据里，属于"代码拼错、用户跟着猜"的典型来源，
  在「Model Registry」手工填写时对不上就会在运行期变成 Agent 的
  「Agent 生成回答失败」。

因此代码侧规范键统一为 ``agnes``（``app/core/config.py::LLM_PROVIDERS``），
历史 ``agens`` 仅作为别名接受。本迁移负责把**已被上一版归一成 agens 的历史数据**
再收敛一次，并覆盖其余常见拼写；``upgrade`` 全部是幂等 ``UPDATE``，重复执行无副作用。

代码侧别名解析见 ``app/core/config.py::normalize_provider`` / ``PROVIDER_ALIASES``，
写入口校验见 ``app/schemas/llm_model.py``。

Revision ID: b7c1d5e9a3f2
Revises: f1a7b3c2d9e4
Create Date: 2026-10-03
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c1d5e9a3f2"
down_revision = "f1a7b3c2d9e4"
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
    """把历史拼写收敛到规范键 ``agnes``（对 SQLite / PostgreSQL 都可用）。"""
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
