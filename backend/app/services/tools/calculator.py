"""calculator 工具 —— 安全的数学表达式求值（审计 §4「一个真实场景」之二）。

不引入任何新依赖，也**不使用** ``eval`` / ``exec``：表达式先经 ``ast.parse``，
再按白名单递归求值。拒绝的内容包括属性访问、下标、变量、导入、Lambda、
推导式、f-string 与任何非白名单函数调用 —— 即"能算出结果"的前提下，把表达式
当成数据而不是代码。

求值前还有一道"宽容但同一套规则"的预处理：参数值如果是 ``1+2是多少`` 这类
**自然语言问句**，先交给 :func:`~app.services.math_intent.extract_math_expression`
（Agent 规划器 / Workflow ``input_is_math`` 条件用的是同一份规则）把表达式取出来，
取不出才报语法错误。返回值里 ``expression`` 是**实际参与求值**的表达式，
``input_expression`` 是收到的原文，两边可对照。

算力保护（否则 ``9**9**9`` 就能让 worker 卡死）：
- 表达式长度上限 ``settings.TOOL_CALCULATOR_MAX_CHARS``；
- AST 节点数上限与幂指数上限；
- 结果必须是有限实数（NaN / inf / 复数一律拒绝）；
- 执行超时由 :class:`~app.services.tools.registry.ToolRegistry` 统一兜底。
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

from ...core.config import settings
from ..math_intent import extract_math_expression
from .base import BaseTool, ToolContext, ToolInvalidArguments

# 二元 / 一元运算符白名单
_ALLOWED_BINARY_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# 函数白名单：全部来自标准库 math / builtins 的纯函数
_ALLOWED_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "floor": math.floor,
    "ceil": math.ceil,
    "fabs": math.fabs,
    "factorial": math.factorial,
}
# 常量白名单
_ALLOWED_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

_MAX_NODES = 60          # AST 节点上限
_MAX_POW_EXPONENT = 100  # 幂指数上限（含负号，取下限 -100）


class CalculatorTool(BaseTool):
    """数学表达式计算器。"""

    name = "calculator"
    description = (
        "计算数学表达式，支持 + - * / // % ** 与括号，以及 sqrt/log/abs/round/"
        "min/max/sin/cos/tan 等白名单函数和常量 pi、e。不接受变量、属性访问或代码；"
        "参数值也可以是含表达式的自然语言问句（如「1+2是多少」），会按统一规则先取出表达式。"
    )

    @property
    def parameters(self) -> dict[str, dict[str, Any]]:  # type: ignore[override]
        return {
            "expression": {
                "type": "string",
                "required": True,
                "description": (
                    "待计算的数学表达式，例如 (1+2)*3 或 sqrt(16)+pi；"
                    "也接受「1+2是多少」这类问句（会先取出 1+2）"
                ),
                "maxLength": settings.TOOL_CALCULATOR_MAX_CHARS,
            }
        }

    async def run(self, context: ToolContext, expression: str = "", **_: Any) -> dict[str, Any]:
        expression = expression.strip()
        input_expression = expression
        max_chars = settings.TOOL_CALCULATOR_MAX_CHARS
        if len(expression) > max_chars:
            raise ToolInvalidArguments(f"表达式长度不能超过 {max_chars} 字符")

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            # 收到的可能是「1+2是多少」这类问句（Workflow 用 {{input}} 透传时很常见）：
            # 用与 Agent 规划器**同一套**规则把表达式取出来；取不出就报原来的语法错误。
            extracted = extract_math_expression(expression)
            if not extracted or extracted == expression:
                raise ToolInvalidArguments(f"表达式语法错误: {exc.msg}") from exc
            expression = extracted
            try:
                tree = ast.parse(expression, mode="eval")
            except SyntaxError as inner:
                raise ToolInvalidArguments(f"表达式语法错误: {inner.msg}") from inner

        nodes = list(ast.walk(tree))
        if len(nodes) > _MAX_NODES:
            raise ToolInvalidArguments("表达式过于复杂")

        try:
            value = _evaluate(tree.body)
        except ToolInvalidArguments:
            raise
        except ZeroDivisionError:
            raise ToolInvalidArguments("除数不能为零")
        except OverflowError:
            raise ToolInvalidArguments("计算结果溢出")
        except (ValueError, TypeError) as exc:
            # math 域错误：sqrt(-1)、log(0)、factorial 负数等
            raise ToolInvalidArguments(f"表达式无法计算: {exc}") from exc

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ToolInvalidArguments("表达式结果必须是数值")
        if isinstance(value, float) and not math.isfinite(value):
            raise ToolInvalidArguments("表达式结果不是有限数值")

        return {
            "expression": expression,
            "input_expression": input_expression,
            "result": value,
            "formatted": f"{value}",
            "result_type": "int" if isinstance(value, int) else "float",
        }


def _evaluate(node: ast.AST) -> Any:
    """按白名单递归求值；命中任何不支持的语法即拒绝。"""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolInvalidArguments("表达式只允许数值常量")
        return node.value

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINARY_OPS:
            raise ToolInvalidArguments(f"不支持运算符: {op_type.__name__}")
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if op_type is ast.Pow:
            if not isinstance(right, (int, float)) or abs(right) > _MAX_POW_EXPONENT:
                raise ToolInvalidArguments(
                    f"幂指数绝对值不能超过 {_MAX_POW_EXPONENT}"
                )
        return _ALLOWED_BINARY_OPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY_OPS:
            raise ToolInvalidArguments(f"不支持运算符: {op_type.__name__}")
        return _ALLOWED_UNARY_OPS[op_type](_evaluate(node.operand))

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.id]
        raise ToolInvalidArguments(f"不支持的变量: {node.id}")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ToolInvalidArguments("只允许调用白名单函数")
        func = _ALLOWED_FUNCTIONS.get(node.func.id)
        if func is None:
            raise ToolInvalidArguments(f"不支持的函数: {node.func.id}")
        if node.keywords:
            raise ToolInvalidArguments("函数调用不支持关键字参数")
        return func(*[_evaluate(arg) for arg in node.args])

    raise ToolInvalidArguments(
        f"表达式包含不支持的语法: {type(node).__name__}"
    )
