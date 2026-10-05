"""Workflow API 的请求 / 响应 Schema（审计 §4）。

字段与 ``app/models/workflow.py`` 的 ``steps`` 一一对应；执行响应刻意暴露**执行
过程**（逐步 ``steps``、``skipped`` + ``skip_reason``、``aborted`` / ``aborted_at``），
因为审计点名的坏味道正是"结果看起来正常、过程完全不可见"。

与 Agent 的契约保持同一形状（``steps[].{tool, ok, output, error, elapsed_ms}``），
前端可以用同一套渲染逻辑；多出来的 ``skipped`` / ``skip_reason`` 用于**条件分支**
被跳过的情况 —— 跳过必须可见。

编排上限（``WORKFLOW_MAX_STEPS`` / 单次输入长度）同时通过
``GET /api/workflows/limits`` 暴露给前端：页面据此显示"最多 N 步"并在到达上限时
禁用"添加步骤"，而不是让用户填完一大堆步骤后才在保存时收到一句英文 422。
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..core.config import settings

#: 单次执行的输入长度上限（``/execute`` 与 ``GET /api/workflows/limits`` 共用同一常量）
MAX_INPUT_CHARS = 2000


class WorkflowStep(BaseModel):
    """单个步骤（同时用于请求体与响应体）。"""

    id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="步骤标识（同一 Workflow 内唯一），供后续步骤用 {{steps.<id>.output.*}} 引用",
    )
    tool: str = Field(..., min_length=1, description="工具名（须在 GET /api/tools 中已注册）")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "工具参数；字符串值里可用 {{input}} 与 {{steps.<步骤ID>.output.<字段>}} 占位符"
        ),
    )
    when: Literal[
        "always", "previous_succeeded", "previous_failed", "input_is_math"
    ] = Field(
        "always", description="执行条件（不满足则跳过，并在响应里给出 skip_reason）"
    )
    on_error: Literal["abort", "continue"] = Field(
        "abort", description="该步失败后的动作：abort 中止整条流程 / continue 继续后续步骤"
    )


class WorkflowCreate(BaseModel):
    """创建 Workflow 的请求体。"""

    name: str = Field(..., min_length=1, max_length=100, description="Workflow 名称")
    description: Optional[str] = Field(None, description="用途说明")
    steps: list[WorkflowStep] = Field(
        ...,
        min_length=1,
        max_length=settings.WORKFLOW_MAX_STEPS,
        description=f"有序步骤清单（最多 {settings.WORKFLOW_MAX_STEPS} 步）",
    )
    enabled: bool = Field(True, description="是否启用")


class WorkflowUpdate(BaseModel):
    """更新 Workflow 的请求体（只更新显式给出的字段）。"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    steps: Optional[list[WorkflowStep]] = Field(
        None, min_length=1, max_length=settings.WORKFLOW_MAX_STEPS
    )
    enabled: Optional[bool] = None


class WorkflowResponse(BaseModel):
    """Workflow 详情 / 列表项。"""

    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    steps: list[WorkflowStep] = Field(default_factory=list)
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkflowExecuteRequest(BaseModel):
    """执行 Workflow 的请求体。"""

    input: str = Field(
        ...,
        min_length=1,
        max_length=MAX_INPUT_CHARS,
        description="本次执行的输入（可用 {{input}} 在步骤参数里引用）",
    )


class WorkflowLimitsResponse(BaseModel):
    """编排 / 执行上限（前端据此做前置提示，不靠硬编码）。"""

    max_steps: int = Field(..., description="单条 Workflow 的步骤上限（settings.WORKFLOW_MAX_STEPS）")
    max_input_chars: int = Field(..., description="单次执行输入的长度上限")
    tools: list[str] = Field(
        default_factory=list, description="已注册工具名（与 GET /api/tools 同一份注册表）"
    )


class WorkflowStepResult(BaseModel):
    """单步执行结果（成功 / 失败 / 被跳过同一形状，便于前端统一渲染）。"""

    id: str
    tool: str
    ok: bool = False
    skipped: bool = Field(False, description="是否因 when 条件不成立被跳过")
    skip_reason: Optional[str] = Field(None, description="被跳过时的原因（不静默跳过）")
    output: Optional[dict[str, Any]] = None
    error: Optional[dict[str, str]] = None
    elapsed_ms: int = 0


class WorkflowExecuteResponse(BaseModel):
    """执行结果：逐步轨迹 + 汇总。"""

    workflow_id: int
    workflow_name: str
    input: str
    steps: list[WorkflowStepResult] = Field(default_factory=list)
    completed: int = Field(0, description="成功执行的步骤数")
    skipped: int = Field(0, description="被条件跳过的步骤数")
    aborted: bool = Field(False, description="是否因某一步失败而中止")
    aborted_at: Optional[str] = Field(None, description="中止发生在那一步的 id")
    max_steps: int = Field(..., description="本次执行生效的步骤上限")
    warnings: list[str] = Field(default_factory=list, description="跳过 / 失败 / 降级说明")
    elapsed_ms: int = 0
