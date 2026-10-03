"""Workflow 执行器 —— 顺序步骤 + 条件分支 + 状态传递 + 失败处理（审计 §4）。

执行链路（每一步都能在响应体里看到）：

1. 启用校验 → 未启用直接 409（不返回空结果假装"没有输出"）；
2. 步骤清单校验 → 空清单 400 ``WORKFLOW_NOT_CONFIGURED``；超过
   ``settings.WORKFLOW_MAX_STEPS`` 直接 400（不静默截断用户的流程）；
3. 逐步执行：
   * ``when`` 条件不成立 → **跳过**并记录 ``skip_reason``（不静默跳过）；
   * 参数里的 ``{{input}}`` / ``{{steps.<id>.output.<字段>}}`` 由
     :mod:`app.services.workflow.templating` 解析（**状态**传递）；
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
from ..tools import ToolContext, ToolError
from ..tools import tool_registry as default_tool_registry
from .errors import WorkflowDisabled, WorkflowInvalidStep, WorkflowNotConfigured
from .templating import TemplateError, evaluate_condition, resolve_value

#: 参数模板解析失败时该步的错误码（与工具层的 TOOL_* 区分开，便于按码排查）
TEMPLATE_ERROR_CODE = "WORKFLOW_TEMPLATE_ERROR"


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
