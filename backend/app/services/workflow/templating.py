"""Workflow 的**状态传递**（模板变量）与**条件分支**（审计 §4「Workflow」）。

审计要求 Workflow 覆盖"多个步骤、条件分支、状态和失败处理"：

* **状态** —— 前面步骤的输出通过占位符喂给后面步骤，而不是靠全局变量或隐式约定：

  ================================  ==========================================
  ``{{input}}``                     本次执行的输入（原样）
  ``{{steps.<id>.ok}}``             该步骤是否成功（bool）
  ``{{steps.<id>.output.<路径>}}``  该步骤的工具输出（点号路径，数组用下标，如
                                    ``{{steps.search.output.snippets.0.content}}``）
  ``{{steps.<id>.error.code}}``     该步骤失败时的错误码（``.message`` 同理）
  ================================  ==========================================

  解析规则刻意"严格"：整个字符串就是一个占位符时保留**原始类型**（数字仍是
  数字），混在文本里的占位符则转成字符串；引用不存在的步骤 / 字段**直接报错**，
  不做"原样透传"——否则工具会收到字面量 ``{{...}}`` 并返回一个看不懂的 400。

* **条件分支** —— ``when`` 支持 ``always`` / ``previous_succeeded`` /
  ``previous_failed`` / ``input_is_math``。最后一项目复用 Agent 规划器的
  :func:`~app.services.agent.planner.extract_math_expression`（同一份识别规则，
  不新增第二套"是不是数学题"的判断）。

被跳过的步骤会带 ``skip_reason`` 出现在响应里，绝不静默跳过。
"""

from __future__ import annotations

import re
from typing import Any

from ..agent.planner import extract_math_expression

#: ``{{ 引用 }}``；内部不允许出现大括号，避免跨占位符误匹配
PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

#: 允许的引用根（写错根名时给出的提示就是它）
_REFERENCE_ROOTS = ("input", "steps")

WHEN_ALWAYS = "always"
WHEN_PREVIOUS_SUCCEEDED = "previous_succeeded"
WHEN_PREVIOUS_FAILED = "previous_failed"
WHEN_INPUT_IS_MATH = "input_is_math"

#: ``when`` 取值（与 ``app/schemas/workflow.py`` 的 Literal 保持一致）
WHEN_CHOICES: tuple[str, ...] = (
    WHEN_ALWAYS,
    WHEN_PREVIOUS_SUCCEEDED,
    WHEN_PREVIOUS_FAILED,
    WHEN_INPUT_IS_MATH,
)

#: ``on_error`` 取值
ON_ERROR_CHOICES: tuple[str, ...] = ("abort", "continue")


class TemplateError(Exception):
    """占位符无法解析（未知引用 / 路径不存在 / 引用了被跳过的步骤）。"""


def _describe_reference(expression: str) -> str:
    """把表达式还原成 ``{{...}}`` 形式，报错时能直接给用户看。"""
    return "{{" + expression + "}}"


def _walk_path(current: Any, path: list[str], expression: str) -> Any:
    """按点号路径取子值；任一段缺失都报错（绝不返回"静默的 None"）。"""
    for key in path:
        if isinstance(current, dict):
            if key not in current:
                raise TemplateError(
                    f"{_describe_reference(expression)} 的字段不存在: {key}"
                    f"（可用字段: {', '.join(sorted(current)) or '无'}）"
                )
            current = current[key]
        elif isinstance(current, list):
            if not key.isdigit() or int(key) >= len(current):
                raise TemplateError(
                    f"{_describe_reference(expression)} 的数组下标非法: {key}"
                    f"（当前长度 {len(current)}）"
                )
            current = current[int(key)]
        else:
            raise TemplateError(
                f"{_describe_reference(expression)} 无法继续取值: {key}"
                f"（当前类型 {type(current).__name__}）"
            )
    return current


def _resolve_expression(expression: str, state: dict[str, Any]) -> Any:
    """解析单个占位符表达式（``input`` / ``steps.<id>.<字段>``）。"""
    parts = [part for part in expression.split(".") if part != ""]
    if not parts:
        raise TemplateError(f"空引用: {_describe_reference(expression)}")

    if parts[0] not in _REFERENCE_ROOTS:
        raise TemplateError(
            f"未知引用 {_describe_reference(expression)}："
            "可用 {{input}}、{{steps.<步骤ID>.output.<字段>}}、"
            "{{steps.<步骤ID>.ok}}、{{steps.<步骤ID>.error.code}}"
        )

    if parts[0] == "input":
        if len(parts) > 1:
            raise TemplateError(
                f"{_describe_reference(expression)} 只能整体引用 {{input}}，"
                "不支持对输入取字段"
            )
        return state["input"]

    # parts[0] == "steps"
    if len(parts) < 3:
        raise TemplateError(
            f"{_describe_reference(expression)} 不完整："
            "应为 {{steps.<步骤ID>.output.<字段>}} / {{steps.<步骤ID>.ok}} / "
            "{{steps.<步骤ID>.error.code}}"
        )

    step_id = parts[1]
    entry = state["steps"].get(step_id)
    if entry is None:
        raise TemplateError(
            f"引用了尚未执行或不存在的步骤: {step_id}"
            f"（已执行: {', '.join(state['steps']) or '无'}）"
        )
    if entry.get("skipped"):
        raise TemplateError(
            f"步骤 {step_id} 本次被条件跳过，没有可用的输出"
            f"（跳过原因: {entry.get('skip_reason') or '未说明'}）"
        )

    field = parts[2]
    if field == "ok":
        if len(parts) != 3:
            raise TemplateError(f"{_describe_reference(expression)} 的 ok 没有下级字段")
        return bool(entry.get("ok"))
    if field == "output":
        if len(parts) == 3:
            return entry.get("output")
        return _walk_path(entry.get("output"), parts[3:], expression)
    if field == "error":
        if len(parts) == 3:
            return entry.get("error")
        return _walk_path(entry.get("error"), parts[3:], expression)

    raise TemplateError(
        f"{_describe_reference(expression)} 的字段非法: {field}"
        "（可用: ok / output / error）"
    )


def resolve_value(value: Any, state: dict[str, Any]) -> Any:
    """把参数里的占位符解析成真实值（递归处理 dict / list）。

    * 字符串**整体**就是一个占位符 → 保留原始类型（数字 / 布尔 / 对象）；
    * 字符串里混有文本 → 占位符替换为字符串；
    * 非字符串（数字 / 布尔 / None）原样返回；dict / list 递归。
    """
    if isinstance(value, str):
        matches = list(PLACEHOLDER_RE.finditer(value))
        if not matches:
            return value
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return _resolve_expression(matches[0].group(1).strip(), state)

        def _replace(match: re.Match[str]) -> str:
            expression = match.group(1).strip()
            resolved = _resolve_expression(expression, state)
            if isinstance(resolved, str):
                return resolved
            if isinstance(resolved, (dict, list)):
                # 结构化值塞进文本里没有意义，直接报错而不是拼出 Python repr
                raise TemplateError(
                    f"{_describe_reference(expression)} 是结构化值，不能拼进字符串，"
                    "请把占位符作为整个参数值"
                )
            return str(resolved)

        return PLACEHOLDER_RE.sub(_replace, value)

    if isinstance(value, dict):
        return {key: resolve_value(item, state) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, state) for item in value]
    return value


def iter_references(value: Any) -> list[str]:
    """收集值里出现过的全部占位符表达式（用于**创建时**校验前向引用）。"""
    found: list[str] = []

    def _collect(item: Any) -> None:
        if isinstance(item, str):
            for match in PLACEHOLDER_RE.finditer(item):
                found.append(match.group(1).strip())
        elif isinstance(item, dict):
            for sub in item.values():
                _collect(sub)
        elif isinstance(item, list):
            for sub in item:
                _collect(sub)

    _collect(value)
    return found


def known_step_references(steps: list[dict[str, Any]]) -> list[str]:
    """校验步骤参数里的 ``steps.<id>`` 引用：只能引用**前面已定义**的步骤。

    Returns:
        问题描述列表（空列表 = 全部合法）。创建 / 更新时用它挡住拼写错误，
        而不是等到执行时才炸。
    """
    problems: list[str] = []
    defined: set[str] = set()
    for index, step in enumerate(steps):
        step_id = str(step.get("id") or f"#{index}")
        for expression in iter_references(step.get("arguments")):
            parts = [part for part in expression.split(".") if part != ""]
            if parts and parts[0] == "input":
                continue
            if not parts or parts[0] != "steps" or len(parts) < 3:
                problems.append(
                    f"步骤 {step_id} 的引用 {{{{{expression}}}}} 格式非法："
                    "应为 {{input}} 或 {{steps.<步骤ID>.output.<字段>}}"
                )
                continue
            referenced = parts[1]
            if referenced not in defined:
                problems.append(
                    f"步骤 {step_id} 引用了不存在或尚未定义的步骤: {referenced}"
                    f"（可引用: {', '.join(sorted(defined)) or '无'}）"
                )
        defined.add(step_id)
    return problems


def evaluate_condition(
    when: str | None,
    previous: dict[str, Any] | None,
    input_text: str,
) -> tuple[bool, str | None]:
    """判断某一步是否执行（条件分支的唯一实现）。

    Returns:
        ``(should_run, skip_reason)``；``should_run=False`` 时 ``skip_reason``
        一定非空（被跳过的步骤会在响应里说明原因，不静默跳过）。
    """
    condition = (when or WHEN_ALWAYS).strip() or WHEN_ALWAYS

    if condition == WHEN_ALWAYS:
        return True, None

    if condition == WHEN_INPUT_IS_MATH:
        if extract_math_expression(input_text) is not None:
            return True, None
        return False, "输入不是可计算的数学表达式（input_is_math 条件不成立）"

    if condition in (WHEN_PREVIOUS_SUCCEEDED, WHEN_PREVIOUS_FAILED):
        if previous is None:
            return False, f"没有前置步骤，{condition} 条件不成立"
        succeeded = bool(previous.get("ok"))
        if condition == WHEN_PREVIOUS_SUCCEEDED:
            if succeeded:
                return True, None
            return False, f"前置步骤 {previous.get('id') or ''} 未成功"
        if not succeeded:
            return True, None
        return False, f"前置步骤 {previous.get('id') or ''} 已成功"

    return False, f"未知的执行条件: {condition}"
