"""Agent 管理 API —— 审计 §4「Agent」的最小真实路径。

审计 §4 原文（改进建议）：

    若实现，只做一个真实场景（KB 检索 + Calculator），必须有 Tool 选择逻辑、
    Tool 超时、最大执行次数、失败处理

本模块把「配置」和「执行」都落到真实资源上：

* ``GET/POST/PUT/DELETE /api/agents`` —— ``agents`` 表（alembic 迁移建表）的
  用户级 CRUD，校验**工具必须已注册**、**知识库必须属于自己**、**模型必须存在且启用**；
* ``POST /api/agents/{id}/execute`` —— 真实执行：工具选择在
  ``app/services/agent/planner.py``，超时/次数/失败处理复用
  ``app/services/tools``（与 ``/api/tools`` 同一份注册表）；
* 执行响应带 ``answer_mode`` 与 ``steps``：未绑定模型时如实返回
  ``tools_only``（工具结果汇总），不冒充"模型生成"。

鉴权：要求登录；所有查询都带 ``user_id == current_user.id``，别人的 Agent 一律
404（不区分"不存在"与"不是你的"，避免探测）。
"""

from fastapi import APIRouter, Depends, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_current_user
from ..core.config import settings
from ..core.exceptions import ValidationError
from ..core.rate_limit import rate_limit
from ..models.agent import Agent
from ..models.knowledge_base import KnowledgeBase
from ..models.llm_model import LLMModel
from ..models.user import User
from ..schemas.agent import (
    AgentCreate,
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentResponse,
    AgentUpdate,
)
from ..services.agent import AgentNotFound, AgentRunner
from ..services.audit_service import create_audit_log
from ..services.tools import ToolContext, tool_registry
from ..storage.database import get_db

router = APIRouter(prefix="/api/agents", tags=["Agent 管理"])

# 执行与问答同档限流：Agent 执行是"每用户每分钟"的重操作（审计 §5.4）
_execute_rate_limit = Depends(
    rate_limit(setting="RATE_LIMIT_CHAT", scope="agents", use_user=True)
)


async def _load_owned_agent(db: AsyncSession, agent_id: int, user_id: int) -> Agent:
    """按 (id, owner) 取 Agent；查不到统一 404。"""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise AgentNotFound(agent_id)
    return agent


async def _validate_configuration(
    db: AsyncSession,
    user_id: int,
    *,
    tools: list[str] | None = None,
    knowledge_base_id: int | None = None,
    model_id: int | None = None,
    max_tool_calls: int | None = None,
) -> None:
    """配置项必须指向**真实存在**的资源，否则 400（不让"看起来配好了"进库）。"""
    if tools is not None:
        unknown = sorted({name for name in tools if name not in tool_registry})
        if unknown:
            raise ValidationError(
                f"未注册的工具: {', '.join(unknown)}"
                f"（可用工具: {', '.join(tool_registry.names())}）"
            )

    if max_tool_calls is not None and max_tool_calls > int(
        settings.TOOL_MAX_CALLS_PER_REQUEST
    ):
        raise ValidationError(
            f"max_tool_calls 不能超过 {int(settings.TOOL_MAX_CALLS_PER_REQUEST)}"
        )

    if knowledge_base_id is not None:
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise ValidationError("知识库不存在或无权访问")

    if model_id is not None:
        result = await db.execute(
            select(LLMModel).where(
                LLMModel.id == model_id, LLMModel.enabled.is_(True)
            )
        )
        if result.scalar_one_or_none() is None:
            raise ValidationError("LLM 模型不存在或未启用")



# 进程内执行器（无状态）；测试通过替换 app.services.agent.runner._build_provider
# 来避免真实 LLM 网络调用，而不是替换执行器本身。
agent_runner = AgentRunner()


@router.get("", response_model=list[AgentResponse], summary="列出当前用户的 Agent")
async def list_agents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """只返回自己的 Agent（按更新时间倒序）。"""
    result = await db.execute(
        select(Agent)
        .where(Agent.user_id == current_user.id)
        .order_by(Agent.updated_at.desc(), Agent.id.desc())
    )
    return [AgentResponse(**agent.to_dict()) for agent in result.scalars().all()]


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent",
)
async def create_agent(
    request: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建 Agent（工具/知识库/模型都必须是真实可用资源）。"""
    await _validate_configuration(
        db,
        current_user.id,
        tools=request.tools,
        knowledge_base_id=request.knowledge_base_id,
        model_id=request.model_id,
        max_tool_calls=request.max_tool_calls,
    )

    agent = Agent(
        user_id=current_user.id,
        name=request.name.strip(),
        description=request.description,
        system_prompt=request.system_prompt,
        knowledge_base_id=request.knowledge_base_id,
        model_id=request.model_id,
        tools=list(dict.fromkeys(request.tools)),
        max_tool_calls=request.max_tool_calls,
        enabled=request.enabled,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="AGENT_CREATE",
        target_type="agent",
        target_id=agent.id,
        detail={"name": agent.name, "tools": list(agent.tools or [])},
        status="SUCCESS",
    )
    logger.info(
        f"Agent created: {agent.name} (id={agent.id}) by user {current_user.username}"
    )
    return AgentResponse(**agent.to_dict())


@router.get("/{agent_id}", response_model=AgentResponse, summary="获取单个 Agent")
async def get_agent(
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取自己的 Agent 详情；非本人 → 404。"""
    agent = await _load_owned_agent(db, agent_id, current_user.id)
    return AgentResponse(**agent.to_dict())


@router.put("/{agent_id}", response_model=AgentResponse, summary="更新 Agent")
async def update_agent(
    agent_id: int,
    request: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """部分更新：只处理请求体里**显式给出**的字段（``exclude_unset``）。"""
    agent = await _load_owned_agent(db, agent_id, current_user.id)
    changes = request.model_dump(exclude_unset=True, exclude_none=False)

    await _validate_configuration(
        db,
        current_user.id,
        tools=changes.get("tools"),
        knowledge_base_id=changes.get("knowledge_base_id"),
        model_id=changes.get("model_id"),
        max_tool_calls=changes.get("max_tool_calls"),
    )

    for field, value in changes.items():
        if field == "name" and isinstance(value, str):
            value = value.strip()
        if field == "tools" and isinstance(value, list):
            value = list(dict.fromkeys(value))
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="AGENT_UPDATE",
        target_type="agent",
        target_id=agent.id,
        detail={"fields": sorted(changes)},
        status="SUCCESS",
    )
    logger.info(f"Agent updated: id={agent.id} fields={sorted(changes)}")
    return AgentResponse(**agent.to_dict())


@router.patch("/{agent_id}", response_model=AgentResponse, summary="部分更新 Agent")
async def patch_agent(
    agent_id: int,
    request: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """PATCH 别名（与 knowledge-bases 的 PUT/PATCH 双入口保持一致）。"""
    return await update_agent(agent_id, request, current_user, db)


@router.delete(
    "/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除 Agent"
)
async def delete_agent(
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除自己的 Agent。"""
    agent = await _load_owned_agent(db, agent_id, current_user.id)
    name = agent.name
    await db.delete(agent)
    await db.commit()
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="AGENT_DELETE",
        target_type="agent",
        target_id=agent_id,
        detail={"name": name},
        status="SUCCESS",
    )
    logger.info(
        f"Agent deleted: {name} (id={agent_id}) by user {current_user.username}"
    )



@router.post(
    "/{agent_id}/execute",
    response_model=AgentExecuteResponse,
    summary="执行 Agent",
    dependencies=[_execute_rate_limit],
)
async def execute_agent(
    agent_id: int,
    request: AgentExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """执行 Agent：规划 → 受限执行（超时/次数/失败即停）→ 汇总回答。

    返回体包含完整轨迹：``plan``、逐步 ``steps``（失败步带 ``error.code``）、
    ``aborted``、``answer_mode``（``llm`` / ``tools_only``）。工具失败**不吞掉**：
    HTTP 仍是 200，但失败信息就在 ``steps`` 与 ``warnings`` 里（与
    ``POST /api/tools/run`` 的语义一致）。
    """
    agent = await _load_owned_agent(db, agent_id, current_user.id)
    result = await agent_runner.run(
        agent,
        request.query,
        ToolContext(user=current_user, db=db),
        top_k=request.top_k,
    )
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="AGENT_EXECUTE",
        target_type="agent",
        target_id=agent.id,
        detail={
            "answer_mode": result["answer_mode"],
            "plan": result["plan"],
            "aborted": result["aborted"],
            "elapsed_ms": result["elapsed_ms"],
        },
        status="SUCCESS" if not result["aborted"] else "FAILURE",
    )
    return AgentExecuteResponse(**result)

