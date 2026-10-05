"""数学意图识别 —— Agent / Workflow / calculator 共用的**唯一**一份规则（审计 §4）。

审计要求 Agent「必须有 Tool 选择逻辑」。判断"这句话是不是一道数学题"这种做法如果
被复制成三份（Agent 规划器、Workflow 的 ``input_is_math`` 条件、calculator 工具），
就会出现"规划器认为不是、执行时又要求表达式"的自相矛盾。因此本模块是唯一实现：

* :func:`~app.services.agent.planner.build_plan` —— 决定要不要把输入交给 calculator；
* :func:`~app.services.workflow.templating.evaluate_condition` —— ``input_is_math``；
* :class:`~app.services.tools.calculator.CalculatorTool` —— 拿到自然语言问句时
  先按本规则把表达式提取出来，再交给 AST 白名单求值。

判据全部是**纯文本检查**，不求值、不引依赖：整句只含 ``0-9 + - * / % ( ) . , 空白``
与白名单标识符（函数 / 常量）、至少一个数字、至少一个运算符或函数调用、括号配平、
长度在 ``settings.TOOL_CALCULATOR_MAX_CHARS`` 以内。

"计算意图"的**首尾措辞**会被裁掉后再判断（这是唯一允许出现中文的地方）：

* 前缀 —— ``请计算``、``计算一下``、``帮我算``、``what is`` … （:data:`_PREFIXES`）；
* 后缀 —— ``等于多少``、``是多少``、``结果是多少``、``equal to`` … （:data:`_TRAILING_NOISE`）。

于是 ``1+2是多少`` / ``计算 1+2 等于多少？`` 会被识别成 ``1+2``，而
``门诊时间是什么时候``（中文出现在表达式位置）、``3 天内回复我``（没有运算符）、
``2026``（没有运算符）依旧判否 —— 保守策略没有被放宽，只是不再把"问法"当成表达式。
"""

from __future__ import annotations

import re

from ..core.config import settings

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

# 结尾的"提问措辞"（中英）：它们是问句的一部分，不是表达式的一部分。
# 只裁这批**封闭**后缀，长度长优先（"的结果是多少" 先于 "是多少"）。
_TRAILING_NOISE: tuple[str, ...] = (
    "的结果是多少",
    "的答案是多少",
    "结果是多少",
    "答案是多少",
    "的值是多少",
    "等于多少呢",
    "等于多少",
    "等于几呢",
    "等于几",
    "是多少呢",
    "是多少",
    "equal to",
    "equals",
)

# 尾部标点（含全角）与空白：裁后缀前先清一遍
_TRAILING_PUNCTUATION = "？?=。.！!；;，,、：: \t\r\n"
# 头部引导标点（"计算：1+1" 之类）
_LEADING_PUNCTUATION = "：:=,， \t\r\n"

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


def _strip_trailing_noise(text: str) -> str:
    """反复裁掉尾部标点与"提问措辞"（``1+2 等于多少？`` → ``1+2``）。

    每次迭代至少少一个字符（或直接返回），因此必然终止；裁完仍然要过
    :data:`_EXPRESSION_RE` 白名单，所以"裁后缀"不会放宽"含中文即判否"的底线。
    """
    current = text
    while True:
        stripped = current.strip().rstrip(_TRAILING_PUNCTUATION).strip()
        lowered = stripped.lower()
        for noise in _TRAILING_NOISE:
            if lowered.endswith(noise):
                stripped = stripped[: -len(noise)]
                break
        else:
            return stripped
        current = stripped


def extract_math_expression(query: str) -> str | None:
    """把"计算意图"的输入转成可交给 calculator 的表达式；无法识别返回 ``None``。"""
    text = (query or "").strip()
    if not text:
        return None

    lowered = text.lower()
    for prefix in _PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix):]
            break

    # 去掉引导标点与结尾的提问措辞 / "=?/。/！"等（这些字符不在表达式白名单里）
    text = _strip_trailing_noise(text.lstrip(_LEADING_PUNCTUATION))
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
