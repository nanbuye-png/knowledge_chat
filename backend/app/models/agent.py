"""Agent 模型 —— 审计 §4「Agent」的最小真实路径。

审计原文（§4）：

    状态：MISSING（后端） + DOC_ONLY（前端与 README）
    改进建议：若实现，只做一个真实场景（KB 检索 + Calculator），必须有
        Tool 选择逻辑、Tool 超时、最大执行次数、失败处理

本表是「实现」而不是「换个说法的假功能」：

* 每行都是一个**真实可执行**的配置：绑定自己的知识库（``knowledge_base_id``）、
  声明允许使用的工具（``tools``）、限定单次执行的工具调用上限
  （``max_tool_calls``）——执行路径见 ``app/services/agent/runner.py``，
  它调用的是与 ``/api/tools`` 同一份 :class:`~app.services.tools.ToolRegistry`
  （超时 / 次数上限 / 失败处理都在那里兜底），**不是**另写一套编排。
* ``model_id`` 为空时不会假装「LLM 已生成」：``tools_only`` 模式返回的是工具
  结果汇总，响应里 ``answer_mode`` 会如实标注（见 ``runner.py``）。

列类型说明：``tools`` 用 JSON（SQLite/PostgreSQL 都支持），Python 侧是
``list[str]`` 工具名；``created_at`` 与 ``api_keys`` 一致，统一存 naive UTC
（审计 §6.1-4：naive/aware 混用会让比较直接抛 TypeError）。
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


class Agent(Base):
    """一个可执行的 Agent 配置（系统提示词 + 知识库 + 工具 + 模型）。"""

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID（归属校验的唯一依据）",
    )
    name = Column(String(100), nullable=False, comment="Agent 名称")
    description = Column(Text, nullable=True, default=None, comment="用途说明")
    system_prompt = Column(
        Text, nullable=True, default=None, comment="系统提示词（LLM 模式下作为 system message）"
    )
    knowledge_base_id = Column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="绑定知识库；kb_search 会按它做归属校验",
    )
    model_id = Column(
        Integer,
        ForeignKey("llm_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="绑定 LLM 模型；为空则只做工具结果汇总（answer_mode=tools_only）",
    )
    tools = Column(
        JSON,
        nullable=False,
        default=list,
        comment="允许使用的工具名列表（只能是注册表里真实存在的工具）",
    )
    max_tool_calls = Column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
        comment="单次执行最多调用工具的次数（执行期还会被 TOOL_MAX_CALLS_PER_REQUEST 收紧）",
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
            "system_prompt": self.system_prompt,
            "knowledge_base_id": self.knowledge_base_id,
            "model_id": self.model_id,
            "tools": list(self.tools or []),
            "max_tool_calls": self.max_tool_calls,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Agent(id={self.id}, name='{self.name}', user_id={self.user_id}, "
            f"tools={list(self.tools or [])}, enabled={self.enabled})>"
        )
