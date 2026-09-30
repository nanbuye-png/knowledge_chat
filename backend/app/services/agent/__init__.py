"""Agent 服务层公开入口（审计 §4）。

组成：

==================  ==========================================================
``planner``         工具选择（确定性规则，可测可解释）
``runner``          受限执行（复用 ``ToolRegistry`` 的超时/次数/失败处理）+ 汇总
``errors``          Agent 层异常（同一套错误契约，不含内部原文）
==================  ==========================================================

Workflow 编排仍未实现（前端与 README 保持 Planned）；Agent 只做
"知识库检索 + 计算器"这一个真实场景。
"""

from .errors import (
    AgentDisabled,
    AgentGenerationFailed,
    AgentNotFound,
    AgentNotConfigured,
)
from .planner import build_plan, effective_max_tool_calls, extract_math_expression
from .runner import AgentRunner

__all__ = [
    "AgentDisabled",
    "AgentGenerationFailed",
    "AgentNotFound",
    "AgentNotConfigured",
    "AgentRunner",
    "build_plan",
    "effective_max_tool_calls",
    "extract_math_expression",
]
