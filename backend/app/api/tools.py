"""
Tool Invocation API —— 工具调用端点（审计 §4）。

只暴露"工具"这一层，不做 Agent 编排：

- ``GET  /api/tools``                    工具清单（含 JSON Schema，供选择逻辑使用）
- ``POST /api/tools/run``                按顺序执行一组调用（次数上限 + 逐步超时 + 失败即停）
- ``POST /api/tools/{tool_name}/invoke`` 单次调用（``{"arguments": {...}}``）
- ``POST /api/tools/{tool_name}``        单次调用的简写（body 直接就是该工具的参数）

鉴权：全部要求登录（``get_current_user``）；``kb_search`` 内部再做知识库归属校验
（审计 §6.2：工具端点不能成为绕过 ``/api/knowledge/query`` 归属校验的越权入口）。

失败处理：工具层异常（``ToolError`` 继承 ``AppError``）由全局异常处理器统一成
``{"code", "message", "request_id"}``；内部异常只落日志，不泄漏原文（审计 §5.5）。
"""

from fastapi import APIRouter, Body, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_current_user
from ..core.config import settings
from ..core.rate_limit import rate_limit
from ..models.user import User
from ..schemas.tool import (
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolListResponse,
    ToolRunRequest,
    ToolRunResponse,
)
from ..services.tools import ToolContext, tool_registry
from ..storage.database import get_db

router = APIRouter(prefix="/api/tools", tags=["工具调用"])

# 复用聊天接口的限流档位：工具调用与问答一样是"每用户每分钟"的重操作，
# 新增一套配额只会让运维更难对齐（审计 §5.4）。
_tool_rate_limit = Depends(
    rate_limit(setting="RATE_LIMIT_CHAT", scope="tools", use_user=True)
)


@router.get(
    "",
    response_model=ToolListResponse,
    summary="列出已实现的工具",
)
async def list_tools(current_user: User = Depends(get_current_user)):
    """返回可被调用的工具及其参数 Schema（选择逻辑的数据来源）。"""
    return ToolListResponse(
        tools=tool_registry.list_tools(),
        max_calls_per_request=int(settings.TOOL_MAX_CALLS_PER_REQUEST),
        timeout_seconds=float(settings.TOOL_TIMEOUT_SECONDS),
    )


@router.post(
    "/run",
    response_model=ToolRunResponse,
    summary="按顺序执行一组工具调用",
    dependencies=[_tool_rate_limit],
)
async def run_tools(
    request: ToolRunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按给定顺序逐个执行工具调用。

    返回体是**逐步结果**而不是"一次性成败"：某一步失败时中止（``aborted=true``），
    已完成步骤的结果仍然返回，失败步骤带 ``error.code`` / ``error.message``。
    超过 ``TOOL_MAX_CALLS_PER_REQUEST`` 或列表格式非法 → 400。
    """
    plan = await tool_registry.run_plan(
        [call.dict() for call in request.calls],
        ToolContext(user=current_user, db=db),
    )
    if plan["aborted"]:
        logger.warning(
            f"工具计划中止: user_id={current_user.id} completed={plan['completed']}"
        )
    return plan


@router.post(
    "/{tool_name}/invoke",
    response_model=ToolInvokeResponse,
    summary="调用单个工具",
    dependencies=[_tool_rate_limit],
)
async def invoke_tool(
    tool_name: str,
    request: ToolInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """调用单个工具；工具不存在 404、参数非法 400、超时 504。"""
    result = await tool_registry.invoke(
        tool_name,
        request.arguments,
        ToolContext(user=current_user, db=db),
    )
    return result.to_dict()


@router.post(
    "/{tool_name}",
    response_model=ToolInvokeResponse,
    summary="调用单个工具（简写形式）",
    dependencies=[_tool_rate_limit],
)
async def invoke_tool_short(
    tool_name: str,
    arguments: dict = Body(default={}, description="该工具的参数对象"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """``POST /api/tools/kb_search`` 的简写：body 直接就是工具参数。"""
    result = await tool_registry.invoke(
        tool_name,
        arguments,
        ToolContext(user=current_user, db=db),
    )
    return result.to_dict()
