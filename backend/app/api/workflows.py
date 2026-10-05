"""Workflow 编排 API —— 审计 §4「Workflow」的最小真实路径。

与 Agent 的分工（同一份 README / ``docs/architecture.md`` 口径）：

* **Agent** = 动态规划 + 工具选择 + 循环（``app/api/agents.py``）；
* **Workflow** = 用户**显式声明**的有序步骤 + 条件分支 + 状态传递 + 失败处理。

端点：

* ``GET/POST/PUT/PATCH/DELETE /api/workflows`` —— ``workflows`` 表（alembic 迁移
  建表）的用户级 CRUD；
* ``POST /api/workflows/{id}/execute`` —— 真实执行：逐步调用
  ``app/services/workflow/runner.py``，工具执行复用
  ``app/services/tools``（与 ``/api/tools``、Agent 同一份注册表，含超时与失败包装）。

写入口的四道校验（**不让"看起来配好了"进库**）：

1. 步骤里的工具必须在注册表中（与 ``GET /api/tools`` 一致）；
2. 步骤 ``id`` 唯一；
3. 参数里的 ``{{steps.<id>...}}`` 只能引用**前面已定义**的步骤（拼错即 400，
   而不是等到执行时才炸）；
4. **必填参数不能留空**：执行器只会自动补齐
   :data:`~app.services.workflow.INPUT_FILLED_ARGUMENTS` 声明的参数（
   calculator 的 ``expression``、kb_search 的 ``query`` —— 它们"要的就是本次输入"），
   其余必填参数缺失就是"存进去也必然失败"（典型是 kb_search 的
   ``knowledge_base_id``：数据归属，不能替用户猜），保存时直接 400 并给出照做的写法。

鉴权：要求登录；所有查询都带 ``user_id == current_user.id``，别人的 Workflow
一律 404（不区分"不存在"与"不是你的"，避免探测）。
"""

from fastapi import APIRouter, Depends, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import get_current_user
from ..core.config import settings
from ..core.exceptions import ValidationError
from ..core.rate_limit import rate_limit
from ..models.user import User
from ..models.workflow import Workflow
from ..schemas.workflow import (
    MAX_INPUT_CHARS,
    WorkflowCreate,
    WorkflowExecuteRequest,
    WorkflowExecuteResponse,
    WorkflowLimitsResponse,
    WorkflowResponse,
    WorkflowUpdate,
)
from ..services.audit_service import create_audit_log
from ..services.tools import ToolContext, tool_registry
from ..services.workflow import (
    INPUT_FILLED_ARGUMENTS,
    WorkflowNotFound,
    WorkflowRunner,
    known_step_references,
)
from ..storage.database import get_db

router = APIRouter(prefix="/api/workflows", tags=["Workflow 编排"])

# 执行与问答同档限流：一条 Workflow 可能触发多次工具调用（审计 §5.4）
_execute_rate_limit = Depends(
    rate_limit(setting="RATE_LIMIT_CHAT", scope="workflows", use_user=True)
)


async def _load_owned_workflow(
    db: AsyncSession, workflow_id: int, user_id: int
) -> Workflow:
    """按 (id, owner) 取 Workflow；查不到统一 404。"""
    result = await db.execute(
        select(Workflow).where(
            Workflow.id == workflow_id, Workflow.user_id == user_id
        )
    )
    workflow = result.scalar_one_or_none()
    if workflow is None:
        raise WorkflowNotFound(workflow_id)
    return workflow


def _missing_required_arguments(steps: list[dict]) -> list[str]:
    """列出"必填但没写、执行时也补不上"的参数 —— 不让必然失败的编排进库。

    执行期只会补齐 :data:`~app.services.workflow.INPUT_FILLED_ARGUMENTS` 声明的参数
    （"要的就是本次输入"：calculator 的 ``expression``、kb_search 的 ``query``）；其余
    必填参数缺失就是必然失败。典型例子是 ``kb_search.knowledge_base_id``：它是数据归属，
    不能替用户猜（猜错只会换来一个看不懂的 403），所以保存时就把话说清楚。
    """
    problems: list[str] = []
    for step in steps:
        tool = step["tool"]
        fillable = INPUT_FILLED_ARGUMENTS.get(tool, ())
        spec = tool_registry.get(tool)
        arguments = step["arguments"]
        for name in spec.required_parameters():
            if name in arguments or name in fillable:
                continue
            description = spec.parameters.get(name, {}).get("description") or "无说明"
            problem = (
                f"步骤 {step['id']}（{tool}）缺少必填参数 {name}（{description}）："
                "它不能按本次输入自动取用，请在步骤参数里显式写上"
            )
            if fillable:
                problem += f"（可省略并自动取用的参数：{', '.join(fillable)}）"
            problems.append(problem)
    return problems


def _validate_steps(steps: list[dict]) -> list[dict]:
    """校验步骤清单并归一化（返回可直接入库的 JSON 结构）。"""
    max_steps = int(settings.WORKFLOW_MAX_STEPS)
    if not steps:
        raise ValidationError("Workflow 至少需要一个步骤")
    if len(steps) > max_steps:
        raise ValidationError(f"步骤数不能超过 {max_steps}")

    normalized: list[dict] = []
    seen: set[str] = set()
    for index, step in enumerate(steps):
        step_id = str(step.get("id") or "").strip()
        if not step_id:
            raise ValidationError(f"第 {index + 1} 个步骤缺少 id")
        if step_id in seen:
            raise ValidationError(f"步骤 id 重复: {step_id}")
        seen.add(step_id)

        tool = str(step.get("tool") or "").strip()
        if tool not in tool_registry:
            raise ValidationError(
                f"步骤 {step_id} 使用了未注册的工具: {tool}"
                f"（可用工具: {', '.join(tool_registry.names())}）"
            )

        arguments = step.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValidationError(f"步骤 {step_id} 的 arguments 必须是对象")

        normalized.append(
            {
                "id": step_id,
                "tool": tool,
                "arguments": arguments,
                "when": step.get("when") or "always",
                "on_error": step.get("on_error") or "abort",
            }
        )

    references = known_step_references(normalized)
    if references:
        raise ValidationError("；".join(references))

    problems = _missing_required_arguments(normalized)
    if problems:
        raise ValidationError("；".join(problems))
    return normalized


# 进程内执行器（无状态）；测试可注入替身注册表，不需要替换 API 逻辑
workflow_runner = WorkflowRunner()


@router.get(
    "/limits",
    response_model=WorkflowLimitsResponse,
    summary="编排 / 执行上限",
)
async def get_workflow_limits(current_user: User = Depends(get_current_user)):
    """返回本次部署真正生效的编排上限（前端用它显示"最多 N 步"，不硬编码）。

    路由必须声明在 ``/{workflow_id}`` **之前**，否则 ``limits`` 会被当成
    ``workflow_id`` 去解析（422）。
    """
    return WorkflowLimitsResponse(
        max_steps=int(settings.WORKFLOW_MAX_STEPS),
        max_input_chars=MAX_INPUT_CHARS,
        tools=tool_registry.names(),
    )


@router.get("", response_model=list[WorkflowResponse], summary="列出当前用户的 Workflow")
async def list_workflows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """只返回自己的 Workflow（按更新时间倒序）。"""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.user_id == current_user.id)
        .order_by(Workflow.updated_at.desc(), Workflow.id.desc())
    )
    return [WorkflowResponse(**item.to_dict()) for item in result.scalars().all()]


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Workflow",
)
async def create_workflow(
    request: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建 Workflow（步骤里的工具必须是真实注册的工具，引用必须指向已定义的步骤）。"""
    steps = _validate_steps([step.model_dump() for step in request.steps])

    workflow = Workflow(
        user_id=current_user.id,
        name=request.name.strip(),
        description=request.description,
        steps=steps,
        enabled=request.enabled,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="WORKFLOW_CREATE",
        target_type="workflow",
        target_id=workflow.id,
        detail={"name": workflow.name, "tools": [s["tool"] for s in steps]},
        status="SUCCESS",
    )
    logger.info(
        f"Workflow created: {workflow.name} (id={workflow.id}) "
        f"by user {current_user.username}"
    )
    return WorkflowResponse(**workflow.to_dict())


@router.get("/{workflow_id}", response_model=WorkflowResponse, summary="获取单个 Workflow")
async def get_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取自己的 Workflow 详情；非本人 → 404。"""
    workflow = await _load_owned_workflow(db, workflow_id, current_user.id)
    return WorkflowResponse(**workflow.to_dict())


@router.put("/{workflow_id}", response_model=WorkflowResponse, summary="更新 Workflow")
async def update_workflow(
    workflow_id: int,
    request: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """部分更新：只处理请求体里**显式给出**的字段（``exclude_unset``）。"""
    workflow = await _load_owned_workflow(db, workflow_id, current_user.id)
    changes = request.model_dump(exclude_unset=True, exclude_none=False)

    if changes.get("steps") is not None:
        changes["steps"] = _validate_steps(changes["steps"])
    if isinstance(changes.get("name"), str):
        changes["name"] = changes["name"].strip()

    for field, value in changes.items():
        setattr(workflow, field, value)

    await db.commit()
    await db.refresh(workflow)
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="WORKFLOW_UPDATE",
        target_type="workflow",
        target_id=workflow.id,
        detail={"fields": sorted(changes)},
        status="SUCCESS",
    )
    logger.info(f"Workflow updated: id={workflow.id} fields={sorted(changes)}")
    return WorkflowResponse(**workflow.to_dict())


@router.patch("/{workflow_id}", response_model=WorkflowResponse, summary="部分更新 Workflow")
async def patch_workflow(
    workflow_id: int,
    request: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """PATCH 别名（与 agents / knowledge-bases 的 PUT/PATCH 双入口保持一致）。"""
    return await update_workflow(workflow_id, request, current_user, db)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除 Workflow",
)
async def delete_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除自己的 Workflow。"""
    workflow = await _load_owned_workflow(db, workflow_id, current_user.id)
    name = workflow.name
    await db.delete(workflow)
    await db.commit()
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="WORKFLOW_DELETE",
        target_type="workflow",
        target_id=workflow_id,
        detail={"name": name},
        status="SUCCESS",
    )
    logger.info(
        f"Workflow deleted: {name} (id={workflow_id}) by user {current_user.username}"
    )


@router.post(
    "/{workflow_id}/execute",
    response_model=WorkflowExecuteResponse,
    summary="执行 Workflow",
    dependencies=[_execute_rate_limit],
)
async def execute_workflow(
    workflow_id: int,
    request: WorkflowExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """执行 Workflow：逐步调用工具（条件跳过 / 状态传递 / 失败策略）。

    返回体包含完整轨迹：每一步的 ``output`` / ``error``、被跳过步骤的
    ``skip_reason``、``aborted`` / ``aborted_at``。工具失败**不吞掉**：HTTP 仍是
    200，但失败信息就在 ``steps[].error`` 与 ``warnings`` 里（与
    ``POST /api/tools/run`` 的语义一致）。
    """
    workflow = await _load_owned_workflow(db, workflow_id, current_user.id)
    result = await workflow_runner.run(
        workflow,
        request.input,
        ToolContext(user=current_user, db=db),
    )
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="WORKFLOW_EXECUTE",
        target_type="workflow",
        target_id=workflow.id,
        detail={
            "steps": len(result["steps"]),
            "completed": result["completed"],
            "skipped": result["skipped"],
            "aborted": result["aborted"],
            "aborted_at": result["aborted_at"],
            "elapsed_ms": result["elapsed_ms"],
        },
        status="SUCCESS" if not result["aborted"] else "FAILURE",
    )
    return WorkflowExecuteResponse(**result)

