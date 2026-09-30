"""Agent API 的请求 / 响应 Schema（审计 §4）。

字段与 ``app/models/agent.py`` 一一对应；执行的响应体刻意暴露**执行过程**
（``plan`` / ``steps`` / ``aborted`` / ``answer_mode``），因为审计点名的坏味道
正是"结果看起来正常、过程完全不可见"：

* ``answer_mode`` 如实说明回答是怎么来的（``llm`` = 模型生成，
  ``tools_only`` = 工具结果汇总，未配置模型）；
* ``steps`` 逐步给出工具名 / 是否成功 / 耗时 / 错误码，失败不再被吞掉。
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..core.config import settings


class AgentCreate(BaseModel):
    """创建 Agent 的请求体。"""

    name: str = Field(..., min_length=1, max_length=100, description="Agent 名称")
    description: Optional[str] = Field(None, description="用途说明")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    knowledge_base_id: Optional[int] = Field(None, ge=1, description="绑定知识库 ID")
    model_id: Optional[int] = Field(None, ge=1, description="绑定 LLM 模型 ID")
    tools: list[str] = Field(
        default_factory=list, description="允许使用的工具名（须在 GET /api/tools 中已注册）"
    )
    max_tool_calls: int = Field(
        settings.AGENT_DEFAULT_MAX_TOOL_CALLS,
        ge=1,
        description="单次执行最多调用工具的次数（上限 TOOL_MAX_CALLS_PER_REQUEST）",
    )
    enabled: bool = Field(True, description="是否启用")


class AgentUpdate(BaseModel):
    """更新 Agent 的请求体（只更新显式给出的字段）。"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    knowledge_base_id: Optional[int] = Field(None, ge=1)
    model_id: Optional[int] = Field(None, ge=1)
    tools: Optional[list[str]] = None
    max_tool_calls: Optional[int] = Field(None, ge=1)
    enabled: Optional[bool] = None


class AgentResponse(BaseModel):
    """Agent 详情 / 列表项。"""

    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    knowledge_base_id: Optional[int] = None
    model_id: Optional[int] = None
    tools: list[str] = Field(default_factory=list)
    max_tool_calls: int
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentExecuteRequest(BaseModel):
    """执行 Agent 的请求体。"""

    query: str = Field(..., min_length=1, max_length=2000, description="用户输入")
    top_k: Optional[int] = Field(
        None,
        ge=1,
        le=settings.TOOL_KB_SEARCH_MAX_TOP_K,
        description="kb_search 返回片段数（缺省用工具默认值）",
    )


class AgentStep(BaseModel):
    """单步工具执行结果（结构对齐 ``POST /api/tools/run`` 的逐步结果）。"""

    tool: str
    ok: bool
    output: Optional[dict[str, Any]] = None
    error: Optional[dict[str, str]] = None
    elapsed_ms: int = 0


class AgentExecuteResponse(BaseModel):
    """执行结果：回答 + 完整执行轨迹。"""

    agent_id: int
    agent_name: str
    query: str
    answer: str = Field(..., description="最终回答（llm 生成或工具结果汇总）")
    answer_mode: str = Field(
        ..., description="回答来源：llm（模型生成）/ tools_only（工具结果汇总）"
    )
    model: Optional[str] = Field(None, description="llm 模式下使用的模型名")
    plan: list[str] = Field(default_factory=list, description="实际规划出的工具调用顺序")
    steps: list[AgentStep] = Field(default_factory=list, description="逐步执行结果")
    completed: int = Field(0, description="成功执行的工具调用数")
    aborted: bool = Field(False, description="是否因某一步失败而中止")
    max_tool_calls: int = Field(
        ..., description="本次执行生效的工具调用上限（agent 配置与全局配置取小）"
    )
    citations: list[dict[str, Any]] = Field(default_factory=list)
    snippets: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, description="规划/降级说明（如实标注）")
    elapsed_ms: int = 0
