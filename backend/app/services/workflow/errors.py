"""Workflow 层异常 —— 与工具层 / Agent 层同一套错误契约（审计 §4 / §5.5）。

全部继承 :class:`~app.core.exceptions.AppError`，响应体天然是
``{"code", "message", "request_id"}``；不把内部原文拼进 message。

注意：**工具执行失败不会走到这里**。按本仓库既有语义（``POST /api/tools/run``
与 ``/api/agents/{id}/execute``），单步失败是"流程的一部分"：HTTP 仍是 200，
失败信息落在 ``steps[].error`` 与 ``warnings`` 里，由该步的 ``on_error`` 决定
是否中止。这里只表达"整条流程根本无法开始"的情况。
"""

from ...core.exceptions import AppError


class WorkflowNotFound(AppError):
    """Workflow 不存在或不属于当前用户（对外统一 404，不区分"别人的"）。"""

    def __init__(self, workflow_id: int | None = None):
        super().__init__(
            code="WORKFLOW_NOT_FOUND",
            message="Workflow 不存在"
            + (f": {workflow_id}" if workflow_id is not None else ""),
            status_code=404,
        )


class WorkflowDisabled(AppError):
    """Workflow 已禁用：执行被拒绝（不是"空结果"）。"""

    def __init__(self, name: str = ""):
        super().__init__(
            code="WORKFLOW_DISABLED",
            message=f"Workflow 已禁用，无法执行{': ' + name if name else ''}",
            status_code=409,
        )


class WorkflowNotConfigured(AppError):
    """没有任何可执行步骤。"""

    def __init__(self, message: str = "Workflow 没有任何步骤，无法执行"):
        super().__init__(
            code="WORKFLOW_NOT_CONFIGURED", message=message, status_code=400
        )


class WorkflowInvalidStep(AppError):
    """步骤非法（未注册工具 / 重复 id / 引用不存在的步骤 / 超过步骤上限）。"""

    def __init__(self, message: str):
        super().__init__(
            code="WORKFLOW_INVALID_STEP", message=message, status_code=400
        )
