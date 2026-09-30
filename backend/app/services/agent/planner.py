"""Agent 的工具选择（规划）——确定性规则，不依赖 function calling（审计 §4）。

审计要求"必须有 Tool 选择逻辑"。这里的做法是把选择逻辑写成**可测、可解释**的
确定性规则，而不是把它藏进 LLM 的隐式行为里：

============  ==============================================================
kb_search     绑定了知识库（``agent.knowledge_base_id``）且工具被授权 → 必选
              （Agent 的"落地"能力：回答必须能追溯到知识库片段）
calculator    输入句能识别为数学表达式 → 选；识别不出就不调用（宁可少调，
              也不要把普通问题丢给计算器换回一堆 400）
============  ==============================================================

数学意图识别（:func:`extract_math_expression`）刻意保守，判据全部是纯文本检查，
不求值：整句只含 ``0-9 + - * / % ( ) . , 空白`` 与白名单标识符（函数/常量）、
至少一个数字、至少一个运算符或函数调用、括号配平、长度在
``settings.TOOL_CALCULATOR_MAX_CHARS`` 以内。于是"门诊时间是什么时候"这类
自然语言问题不会被误判成表达式（含中文 → 直接否）。

上限：``agent.max_tool_calls`` 与 ``settings.TOOL_MAX_CALLS_PER_REQUEST``
取小者；被丢弃的步骤写进 ``warnings``，不会静默少执行。
"""

from __future__ import annotations

import re
from typing import Any

from ...core.config import settings

# 常见"计算意图"前缀（中英）；命中即去掉，剩下的部分再按表达式判断
_PREFIXES: tuple[str, ...] = (
    "请计算一下",
    "请计算",
    "帮我计算一下",
    "帮我计算",
    "帮我算一下",
    "帮我算",
    "计算一下",
    "计算",
    "算一下",
    "calculate",
    "compute",
    "what is",
    "what's",
    "whats",
)

# 表达式允许出现的字符：数字 / 字母（白名单标识符）/ 运算符 / 括号 / 逗号 / 空白
_EXPRESSION_RE = re.compile(r"^[0-9A-Za-z_+\-*/%().,\s]+$")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_FUNCTION_CALL_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\s*\(")
_OPERATOR_CHARS = set("+-*/%")

# 与 calculator 工具的白名单保持一致（函数 + 常量），避免"识别通过但调用必失败"
_ALLOWED_IDENTIFIERS: frozenset[str] = frozenset(
    {
        "abs",
        "round",
        "min",
        "max",
        "sum",
        "pow",
        "sqrt",
        "exp",
        "log",
        "log2",
        "log10",
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "floor",
        "ceil",
        "fabs",
        "factorial",
        "pi",
        "e",
        "tau",
    }
)


def extract_math_expression(query: str) -> str | None:
    """把"计算意图"的输入转成可交给 calculator 的表达式；无法识别返回 ``None``。"""
    text = (query or "").strip()
    if not text:
        return None

    lowered = text.lower()
    for prefix in _PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break

    # 去掉引导标点与结尾的"=?/。/！"等（这些字符不在表达式白名单里）
    text = text.strip().lstrip("：:=,，").strip()
    text = text.rstrip("？?=。.！!").strip()
    if not text or len(text) > settings.TOOL_CALCULATOR_MAX_CHARS:
        return None

    if not _EXPRESSION_RE.fullmatch(text):
        return None
    if not any(char.isdigit() for char in text):
        return None
    if text.count("(") != text.count(")"):
        return None

    identifiers = _IDENTIFIER_RE.findall(text)
    if any(identifier.lower() not in _ALLOWED_IDENTIFIERS for identifier in identifiers):
        return None

    has_operator = any(char in _OPERATOR_CHARS for char in text)
    has_call = bool(_FUNCTION_CALL_RE.search(text))
    if not (has_operator or has_call):
        return None

    return text


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
