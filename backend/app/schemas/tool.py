from pydantic import BaseModel, Field
from typing import Any, Optional


class ToolInfo(BaseModel):
    """工具自描述（选择逻辑的数据来源）。"""

    name: str
    description: str
    parameters: dict = Field(default_factory=dict, description="JSON Schema 参数描述")
    required: list[str] = Field(default_factory=list, description="必填参数名")


class ToolListResponse(BaseModel):
    tools: list[ToolInfo] = Field(default_factory=list)
    max_calls_per_request: int = Field(..., description="单次请求最多执行的工具调用次数")
    timeout_seconds: float = Field(..., description="单次工具调用的超时（秒）")


class ToolInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")


class ToolInvokeResponse(BaseModel):
    tool: str
    ok: bool = True
    output: dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: int = 0


class ToolCallSpec(BaseModel):
    tool: str = Field(..., min_length=1, description="工具名")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolRunRequest(BaseModel):
    calls: list[ToolCallSpec] = Field(..., min_length=1, description="按顺序执行的调用列表")


class ToolStepError(BaseModel):
    code: str
    message: str


class ToolStepResult(BaseModel):
    """``/api/tools/run`` 单步结果（成功 / 失败同一形状，便于前端统一渲染）。"""

    tool: str
    ok: bool
    output: Optional[dict] = None
    error: Optional[ToolStepError] = None
    elapsed_ms: int = 0


class ToolRunResponse(BaseModel):
    results: list[ToolStepResult] = Field(default_factory=list, description="逐步结果，含失败项的 error")
    completed: int = Field(0, description="成功执行的调用数")
    aborted: bool = Field(False, description="是否因某一步失败而中止")
    max_calls: int = Field(..., description="本次请求允许的最大调用次数")

