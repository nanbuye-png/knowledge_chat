"""Agent 的工具选择（规划）——确定性规则，不依赖 function calling（审计 §4）。

审计要求"必须有 Tool 选择逻辑"。这里的做法是把选择逻辑写成**可测、可解释**的
确定性规则，而不是把它藏进 LLM 的隐式行为里：

============  ==============================================================
kb_search     绑定了知识库（``agent.knowledge_base_id``）且工具被授权 → 必选
              （Agent 的"落地"能力：回答必须能追溯到知识库片段）
calculator    输入句能识别为数学表达式 → 选；识别不出就不调用（宁可少调，
              也不要把普通问题丢给计算器换回一堆 400）
============  ==============================================================

数学意图识别（:func:`~app.services.math_intent.extract_math_expression`）的**唯一实现**
在 ``app/services/math_intent.py``：判据全部是纯文本检查（白名单字符 / 至少一个数字 /
至少一个运算符或函数调用 / 括号配平 / 长度上限），只裁掉"请计算 … 等于多少"这类
首尾措辞。Agent 规划器、Workflow 的 ``input_is_math`` 条件、calculator 工具共用这一份
规则 —— 不会出现"规划器认为不是数学题、执行时又要求表达式"的三个口径。

这里继续 re-export 这个名字，历史调用点不受影响：``from app.services.agent import
extract_math_expression`` 与 ``from ..agent.planner import extract_math_expression``
都仍然可用。

上限：``agent.max_tool_calls`` 与 ``settings.TOOL_MAX_CALLS_PER_REQUEST``
取小者；被丢弃的步骤写进 ``warnings``，不会静默少执行。
"""

from __future__ import annotations

from typing import Any

from ...core.config import settings
from ..math_intent import extract_math_expression

__all__ = ["build_plan", "effective_max_tool_calls", "extract_math_expression"]

def effective_max_tool_calls(agent: Any) -> int:
    """本次执行真正生效的工具调用上限：``agent.max_tool_calls`` 与全局配置取小。"""
    return max(
        1,
        min(
            int(getattr(agent, "max_tool_calls", 0) or settings.AGENT_DEFAULT_MAX_TOOL_CALLS),
            int(settings.TOOL_MAX_CALLS_PER_REQUEST),
        ),
    )


def build_plan(
    agent: Any,
    query: str,
    registry: Any,
    top_k: int | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """规划工具调用。

    Returns:
        ``(calls, warnings, available_tools)``：

        * ``calls`` — ``[{"tool": ..., "arguments": {...}}]``，顺序即执行顺序；
        * ``warnings`` — 未注册工具 / 超出上限被丢弃的步骤（如实说明）；
        * ``available_tools`` — 该 Agent 配置里**真实可用**的工具名。
    """
    configured = [name for name in (agent.tools or []) if isinstance(name, str)]
    available = [name for name in configured if name in registry]

    warnings: list[str] = []
    missing = [name for name in configured if name not in registry]
    if missing:
        warnings.append(f"以下工具未在注册表中注册，已忽略: {', '.join(sorted(set(missing)))}")

    calls: list[dict[str, Any]] = []

    # 1. 知识库检索：绑定了知识库且工具被授权 → 作为 grounding 步骤
    if agent.knowledge_base_id and "kb_search" in available:
        arguments: dict[str, Any] = {
            "query": query,
            "knowledge_base_id": int(agent.knowledge_base_id),
        }
        if top_k:
            arguments["top_k"] = int(top_k)
        calls.append({"tool": "kb_search", "arguments": arguments})

    # 2. 计算器：仅当输入确实像数学表达式
    if "calculator" in available:
        expression = extract_math_expression(query)
        if expression:
            calls.append(
                {"tool": "calculator", "arguments": {"expression": expression}}
            )

    max_calls = effective_max_tool_calls(agent)
    if len(calls) > max_calls:
        dropped = [call["tool"] for call in calls[max_calls:]]
        calls = calls[:max_calls]
        warnings.append(
            f"计划步骤超过上限 {max_calls}，已丢弃: {', '.join(dropped)}"
        )

    return calls, warnings, available
