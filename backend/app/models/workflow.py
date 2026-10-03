"""Workflow 模型 —— 审计 §4「Workflow」的最小真实路径。

审计原文（§4）：

    状态：MISSING（后端） + DOC_ONLY（前端与 README）
    改进建议：若实现，只做一个真实场景（KB 检索 + Calculator），必须有
        Tool 选择逻辑、Tool 超时、最大执行次数、失败处理

Workflow 与 Agent 的区别（README 与 ``docs/architecture.md`` 的口径一致）：

* **Agent** 是"动态规划 + 工具选择 + 循环"（``app/services/agent``）；
* **Workflow** 是"多个步骤、条件分支、状态和失败处理的组合"，步骤由用户
  **显式声明**，执行顺序确定，不做任何隐式推理。

本表存的是**可执行的步骤清单**（``steps``，JSON 数组），每一步的字段：

=================  ==========================================================
``id``             步骤标识（唯一），供后续步骤引用其输出
``tool``           工具名，必须已在 ``GET /api/tools`` 的注册表中
``arguments``      工具参数，字符串里可用 ``{{input}}`` / ``{{steps.<id>.output.<字段>}}``
``when``           执行条件：``always`` / ``previous_succeeded`` /
                   ``previous_failed`` / ``input_is_math``
``on_error``       该步失败后的动作：``abort``（默认，中止整条流程）/ ``continue``
=================  ==========================================================

执行器见 ``app/services/workflow/runner.py``：它复用与 ``/api/tools``、Agent 相同的
:class:`~app.services.tools.ToolRegistry`（超时 / 失败包装都在那里），**不另写一套
工具执行**；被跳过的步骤会带 ``skip_reason`` 返回，失败步骤带 ``error.code``，
不存在"看起来跑完了其实什么都没做"。

列类型说明：``steps`` 用 JSON（SQLite/PostgreSQL 都支持）；``created_at`` /
``updated_at`` 与 ``agents`` 一致，统一存 naive UTC（审计 §6.1-4：naive/aware
混用会让比较直接抛 TypeError）。
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from ..core.timeutil import utcnow
from .document import Base


class Workflow(Base):
    """一条显式声明的编排流程（有序步骤 + 条件 + 失败策略）。"""

    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID（归属校验的唯一依据）",
    )
    name = Column(String(100), nullable=False, comment="Workflow 名称")
    description = Column(Text, nullable=True, default=None, comment="用途说明")
    steps = Column(
        JSON,
        nullable=False,
        default=list,
        comment="有序步骤清单（tool / arguments / when / on_error），见模块 docstring",
    )
    enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        comment="是否启用；禁用后执行返回 409",
    )
    created_at = Column(DateTime, nullable=False, default=utcnow, comment="创建时间")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        comment="最后更新时间",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "steps": list(self.steps or []),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Workflow(id={self.id}, name='{self.name}', user_id={self.user_id}, "
            f"steps={len(self.steps or [])}, enabled={self.enabled})>"
        )
