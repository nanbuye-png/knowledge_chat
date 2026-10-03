"""工具层公开入口：注册表 + 真实工具（审计 §4）。

当前**已实现**的工具只有两个真实场景：

============  ==========================================================
kb_search     指定知识库内检索（复用生产 RetrievalPipeline，含归属校验）
calculator    数学表达式求值（AST 白名单，不用 eval）
============  ==========================================================

Agent loop 由 ``app/services/agent``（选择 + 受限执行 + 可选 LLM 汇总）承担，
Workflow 编排由 ``app/services/workflow``（显式有序步骤 + 条件分支 + 状态传递 +
失败策略）承担 —— 两者都复用本注册表，工具层自身仍然不做编排。
"""

from .base import (
    BaseTool,
    ToolContext,
    ToolError,
    ToolExecutionError,
    ToolInvalidArguments,
    ToolNotFound,
    ToolPermissionDenied,
    ToolResult,
    ToolTimeout,
)
from .calculator import CalculatorTool
from .kb_search import KnowledgeBaseSearchTool
from .registry import ToolRegistry


def create_tool_registry() -> ToolRegistry:
    """构造并填充默认注册表（测试可自行构造空注册表注册替身）。"""
    registry = ToolRegistry()
    registry.register(KnowledgeBaseSearchTool())
    registry.register(CalculatorTool())
    return registry


# 进程内单例：API 层直接复用（工具本身无状态，除注入的 pipeline 引用）
tool_registry = create_tool_registry()

__all__ = [
    "BaseTool",
    "ToolContext",
    "ToolError",
    "ToolExecutionError",
    "ToolInvalidArguments",
    "ToolNotFound",
    "ToolPermissionDenied",
    "ToolResult",
    "ToolTimeout",
    "ToolRegistry",
    "CalculatorTool",
    "KnowledgeBaseSearchTool",
    "create_tool_registry",
    "tool_registry",
]
