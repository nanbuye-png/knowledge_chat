"""Workflow 执行器 —— 顺序步骤 + 条件分支 + 状态传递 + 失败处理（审计 §4）。

执行链路（每一步都能在响应体里看到）：

1. 启用校验 → 未启用直接 409（不返回空结果假装"没有输出"）；
2. 步骤清单校验 → 空清单 400 ``WORKFLOW_NOT_CONFIGURED``；超过
   ``settings.WORKFLOW_MAX_STEPS`` 直接 400（不静默截断用户的流程）；
3. 逐步执行：
   * ``when`` 条件不成立 → **跳过**并记录 ``skip_reason``（不静默跳过）；
   * 参数里的 ``{{input}}`` / ``{{steps.<id>.output.<字段>}}`` 由
     :mod:`app.services.workflow.templating` 解析（**状态**传递）；
   * 参数补齐由 :func:`apply_argument_defaults` 负责（清单见
     :data:`INPUT_FILLED_ARGUMENTS`）：``calculator`` 步骤没写 ``expression`` 时按
     输入取表达式，``kb_search`` 步骤没写 ``query`` 时原样取用本次输入（补了什么 /
     为什么补不了都会进 ``warnings``，不静默）；
   * 工具调用走 :meth:`ToolRegistry.invoke` —— 超时（``asyncio.wait_for``）、
     参数校验、异常包装全部复用工具层，本模块**不另写一套执行**；
   * 单步失败按该步的 ``on_error`` 处理：``abort``（默认）中止整条流程并记下
     ``aborted_at``；``continue`` 继续后续步骤。失败信息同时进入 ``warnings``。

4. 每一步的结果（含被跳过的步骤）都进入 ``steps``，成功 / 失败 / 跳过同一形状，
   靠 ``ok`` / ``skipped`` 区分，前端可以统一渲染。

刻意不做的事：不内置"假装有思考过程"的伪 CoT；不把失败步骤从 ``steps`` 里抹掉。
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from ...core.config import settings
from ..math_intent import extract_math_expression
from ..tools import ToolContext, ToolError
from ..tools import tool_registry as default_tool_registry
from .errors import WorkflowDisabled, WorkflowInvalidStep, WorkflowNotConfigured
from .templating import TemplateError, evaluate_condition, resolve_value

#: 参数模板解析失败时该步的错误码（与工具层的 TOOL_* 区分开，便于按码排查）
TEMPLATE_ERROR_CODE = "WORKFLOW_TEMPLATE_ERROR"

#: "只有一个明确答案 = 本次输入"的参数：缺失 / 空白时由执行器按输入补齐，不要求用户手填。
#: 写入口（``app/api/workflows.py``）与前端提示共用这一份清单 —— 所以"哪些参数可以留空"
#: 在保存校验、执行补齐、页面提示三处是同一个答案，不会各说一套。
INPUT_FILLED_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "calculator": ("expression",),
    "kb_search": ("query",),
}

#: warning 里引用用户输入时的截断长度（输入可达 2000 字符，不能原样塞进提示）
_PREVIEW_CHARS = 60


def _preview(text: str) -> str:
    """把用户输入压成适合写进 warning 的短预览。"""
    compact = " ".join(text.split())
    return compact if len(compact) <= _PREVIEW_CHARS else f"{compact[:_PREVIEW_CHARS]}…"


def apply_argument_defaults(
    tool: str, arguments: dict[str, Any], input_text: str
) -> tuple[dict[str, Any], str | None]:
    """给"只有一个明确答案"的工具参数补默认值，避免漏填就永远跑不通。

    覆盖 :data:`INPUT_FILLED_ARGUMENTS` 里声明的参数（与写入口共用同一份清单）：

    * ``calculator.expression`` —— 缺失 / 空白时，用与 Agent 规划器、``input_is_math``
      条件**同一套**规则
      （:func:`~app.services.math_intent.extract_math_expression`）从本次输入里取表达式
      —— 于是"一个 calculator 步骤 + 输入 ``1+2是多少``"能直接算出 3，而不是抛
      ``缺少必填参数: expression``；
    * ``kb_search.query`` —— 缺失 / 空白时**原样取用**本次输入：KB 检索的问题就是用户
      输入的自然语言，与 Agent 规划器把 ``query`` 交给 ``kb_search`` 是同一个约定。
      （此前只有 calculator 享受补齐，于是同一个页面上"calculator 留空能跑通、
      kb_search 留空必失败"—— 两套口径已合并，见本模块 docstring。）

    刻意不做的事：不改动用户显式写下的值（含类型写错的情况 —— 那交给工具层按契约
    报 ``类型应为 string``）；**不猜** ``kb_search.knowledge_base_id``（猜不出来也不能
    猜：那是数据归属问题，猜错只会换来一个看不懂的 403）—— 它缺失时只给一条能照做的
    提示，并由写入口直接 400（不让"存进去也必然失败"的编排进库）。

    Returns:
        ``(arguments, warning)``：``warning`` 非空时说明发生了什么（补了什么 /
        为什么补不了），由调用方写进 ``warnings`` —— 自动补齐不静默。
    """
    if tool == "calculator":
        return _fill_calculator_expression(arguments, input_text)
    if tool == "kb_search":
        return _fill_kb_search_arguments(arguments, input_text)
    return arguments, None


def _fill_calculator_expression(
    arguments: dict[str, Any], input_text: str
) -> tuple[dict[str, Any], str | None]:
    """``calculator.expression`` 缺失 / 空白时按输入取表达式（规则与 Agent 规划器同一份）。"""
    expression = arguments.get("expression")
    if isinstance(expression, str) and expression.strip():
        return arguments, None
    if expression is not None and not isinstance(expression, str):
        return arguments, None

    derived = extract_math_expression(input_text)
    if derived is None:
        return arguments, (
            "未提供 expression，且本次输入不是可识别的数学表达式；"
            '请在步骤参数里写 {"expression": "{{input}}"}（输入为纯表达式时直接生效）'
            '或直接写 {"expression": "(1+2)*3"}'
        )

    filled = dict(arguments)
    filled["expression"] = derived
    return filled, (
        f"未提供 expression，已按本次输入自动取用 {derived!r}"
        "（与 Agent 规划器同一套识别规则）"
    )


def _fill_kb_search_arguments(
    arguments: dict[str, Any], input_text: str
) -> tuple[dict[str, Any], str | None]:
    """``kb_search.query`` 缺失 / 空白时取用本次输入；``knowledge_base_id`` 只提示不猜。

    ``knowledge_base_id`` 是数据归属参数（工具层会按当前用户校验归属），猜错只会换来一个
    看不懂的 403 —— 所以这里既不补也不静默：缺了就写进 ``warnings`` 并给一条照做即可的
    指引（写入口还会在保存时直接 400，见 ``app/api/workflows.py``）。
    """
    filled = dict(arguments)
    warnings: list[str] = []

    query = filled.get("query")
    if query is None or (isinstance(query, str) and not query.strip()):
        if input_text.strip():
            filled["query"] = input_text
            warnings.append(
                f"未提供 query，已按本次输入自动取用 {_preview(input_text)!r}"
                "（与 Agent 规划器同一约定；若输入超过 500 字符会被工具拒绝，"
                "请改成显式写 query）"
            )
        else:
            warnings.append(
                "未提供 query，且本次输入为空、无法取用；"
                '请在步骤参数里写 {"query": "{{input}}"} 或一个固定问题'
            )

    if "knowledge_base_id" not in filled:
        warnings.append(
            "未提供 knowledge_base_id：知识库归属不能自动推断，"
            '请在步骤参数里显式写 {"knowledge_base_id": <知识库ID>}'
            "（GET /api/knowledge-bases 可查看自己的知识库 ID）"
        )

    if not warnings:
        return arguments, None
    return filled, "；".join(warnings)



class WorkflowRunner:
    """Workflow 执行器（无状态，可安全复用）。"""

    def __init__(self, registry: Any = None) -> None:
        self._registry = registry or default_tool_registry

    async def run(
        self,
        workflow: Any,
        input_text: str,
        context: ToolContext,
    ) -> dict[str, Any]:
        """执行一条 Workflow，返回"逐步轨迹 + 汇总"。

        Raises:
            WorkflowDisabled: 流程已禁用（409）。
            WorkflowNotConfigured: 没有任何步骤（400）。
            WorkflowInvalidStep: 步骤数超过 ``WORKFLOW_MAX_STEPS``（400）。
        """
        started = time.monotonic()
        if not workflow.enabled:
            logger.warning(f"Workflow 已禁用，拒绝执行: workflow_id={workflow.id}")
            raise WorkflowDisabled(getattr(workflow, "name", ""))

        steps = [step for step in (workflow.steps or []) if isinstance(step, dict)]
        if not steps:
            raise WorkflowNotConfigured(
                f"Workflow {getattr(workflow, 'name', '')} 没有任何步骤"
            )

        max_steps = int(settings.WORKFLOW_MAX_STEPS)
        if len(steps) > max_steps:
            raise WorkflowInvalidStep(
                f"步骤数 {len(steps)} 超过上限 {max_steps}（settings.WORKFLOW_MAX_STEPS）"
            )

        warnings: list[str] = []
        #: 状态容器：input + 已执行步骤的 {ok, output, error}，供后续步骤引用
        state: dict[str, Any] = {"input": input_text, "steps": {}}
        results: list[dict[str, Any]] = []
        completed = 0
        skipped = 0
        aborted = False
        aborted_at: str | None = None
        previous: dict[str, Any] | None = None

        for index, step in enumerate(steps):
            step_id = str(step.get("id") or f"step_{index + 1}")
            tool = str(step.get("tool") or "")
            on_error = str(step.get("on_error") or "abort")

            should_run, skip_reason = evaluate_condition(
                step.get("when"), previous, input_text
            )
            if not should_run:
                reason = skip_reason or "条件不成立"
                entry = self._entry(step_id, tool, skipped=True, skip_reason=reason)
                results.append(entry)
                state["steps"][step_id] = {
                    "ok": False,
                    "output": None,
                    "error": None,
                    "skipped": True,
                    "skip_reason": reason,
                }
                skipped += 1
                warnings.append(f"步骤 {step_id} 已跳过：{reason}")
                previous = entry
                continue

            entry = self._entry(step_id, tool)
            step_started = time.monotonic()

            try:
                arguments = resolve_value(step.get("arguments") or {}, state)
            except TemplateError as exc:
                entry["error"] = {"code": TEMPLATE_ERROR_CODE, "message": str(exc)}
                entry["elapsed_ms"] = int((time.monotonic() - step_started) * 1000)
                results.append(entry)
                state["steps"][step_id] = {
                    "ok": False,
                    "output": None,
                    "error": entry["error"],
                    "skipped": False,
                    "skip_reason": None,
                }
                warnings.append(f"步骤 {step_id}（{tool}）参数解析失败：{exc}")
                previous = entry
                if on_error == "abort":
                    aborted, aborted_at = True, step_id
                    break
                continue

            arguments, default_warning = apply_argument_defaults(tool, arguments, input_text)
            if default_warning:
                warnings.append(f"步骤 {step_id}（{tool}）：{default_warning}")

            try:
                result = await self._registry.invoke(tool, arguments, context)
            except ToolError as exc:
                # 工具层异常是"这一步失败"，不是整个请求失败（与 /api/tools/run 一致）
                entry["error"] = {"code": exc.code, "message": exc.message}
            else:
                entry["ok"] = True
                entry["output"] = dict(result.output)
                completed += 1

            entry["elapsed_ms"] = int((time.monotonic() - step_started) * 1000)
            results.append(entry)
            state["steps"][step_id] = {
                "ok": entry["ok"],
                "output": entry["output"],
                "error": entry["error"],
                "skipped": False,
                "skip_reason": None,
            }
            previous = entry

            if entry["ok"]:
                logger.debug(f"Workflow 步骤成功: {step_id} tool={tool}")
                continue

            error = entry["error"] or {}
            warnings.append(
                f"步骤 {step_id}（{tool}）失败（{error.get('code', 'TOOL_ERROR')}）："
                f"{error.get('message', '')}"
            )
            if on_error == "abort":
                aborted = True
                aborted_at = step_id
                break

        logger.info(
            f"Workflow 执行完成: id={workflow.id} steps={len(results)} "
            f"completed={completed} skipped={skipped} aborted={aborted}"
        )
        return {
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "input": input_text,
            "steps": results,
            "completed": completed,
            "skipped": skipped,
            "aborted": aborted,
            "aborted_at": aborted_at,
            "max_steps": max_steps,
            "warnings": warnings,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    @staticmethod
    def _entry(
        step_id: str,
        tool: str,
        *,
        skipped: bool = False,
        skip_reason: str | None = None,
    ) -> dict[str, Any]:
        """构造一条逐步结果（成功 / 失败 / 跳过同一形状）。"""
        return {
            "id": step_id,
            "tool": tool,
            "ok": False,
            "skipped": skipped,
            "skip_reason": skip_reason,
            "output": None,
            "error": None,
            "elapsed_ms": 0,
        }
