from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ...core.permissions import require_permission
from ...models.user import User
from ...models.knowledge_base import KnowledgeBase
from ...models.document import Document
from ...models.conversation import Conversation
from ...models.message import Message
from ...models.llm_usage import LLMUsage
from ...services.system_monitor import get_system_metrics
from ...storage.database import get_db

router = APIRouter(prefix="/api/admin", tags=["管理员-Dashboard"])


# ---------- Schemas ----------

class DashboardOverviewResponse(BaseModel):
    users_count: int
    knowledge_bases_count: int
    documents_count: int
    conversations_count: int
    messages_count: int


class SystemMonitorResponse(BaseModel):
    cpu_usage: float | None
    memory_usage: float | None
    disk_usage: float | None
    uptime: str | None
    python_version: str | None
    platform: str | None
    timestamp: str | None


# ---------- Helper ----------

def _today_range() -> tuple[datetime, datetime]:
    """返回今天 UTC 的开始和结束时间。"""
    today = date.today()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    end = datetime(today.year, today.month, today.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return start, end


# ---------- Endpoint ----------

@router.get("/dashboard", summary="系统概览统计")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:view")),
):
    """获取系统概览统计信息（需要 dashboard:view 权限）。"""
    # 1. 用户统计（仅统计未软删除用户）
    total_result = await db.execute(
        select(func.count(User.id)).where(User.deleted_at.is_(None))
    )
    total_users = total_result.scalar() or 0

    active_result = await db.execute(
        select(func.count(User.id)).where(
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    active_users = active_result.scalar() or 0

    disabled_result = await db.execute(
        select(func.count(User.id)).where(
            User.deleted_at.is_(None),
            User.is_active.is_(False),
        )
    )
    disabled_users = disabled_result.scalar() or 0

    root_result = await db.execute(
        select(func.count(User.id)).where(
            User.deleted_at.is_(None),
            User.role == "ROOT",
        )
    )
    root_count = root_result.scalar() or 0

    admin_result = await db.execute(
        select(func.count(User.id)).where(
            User.deleted_at.is_(None),
            User.role == "ADMIN",
        )
    )
    admin_count = admin_result.scalar() or 0

    # 2. 知识库统计
    kb_result = await db.execute(
        select(func.count(KnowledgeBase.id))
    )
    knowledge_total = kb_result.scalar() or 0

    # 3. 文档统计
    doc_result = await db.execute(
        select(func.count(Document.id))
    )
    documents_total = doc_result.scalar() or 0

    # 4. 在线用户统计（最近 5 分钟有活动）
    from datetime import timedelta
    five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    online_result = await db.execute(
        select(func.count(User.id)).where(
            User.deleted_at.is_(None),
            User.last_activity_at >= five_minutes_ago,
        )
    )
    online_users = online_result.scalar() or 0

    # 5. Usage 统计（当天数据）
    today_start, today_end = _today_range()
    usage_today_result = await db.execute(
        select(
            func.count(LLMUsage.id),
            func.coalesce(func.sum(LLMUsage.prompt_tokens), 0),
            func.coalesce(func.sum(LLMUsage.completion_tokens), 0),
            func.coalesce(func.sum(LLMUsage.total_tokens), 0),
        ).where(
            LLMUsage.created_at >= today_start,
            LLMUsage.created_at <= today_end,
        )
    )
    usage_row = usage_today_result.one()
    today_requests = usage_row[0] or 0
    today_prompt_tokens = usage_row[1] or 0
    today_completion_tokens = usage_row[2] or 0
    today_total_tokens = usage_row[3] or 0

    # 6. Chunk 统计（ChromaDB）
    chunks_total = 0
    embeddings_total = 0
    try:
        from ...storage.vector_store import vector_store
        if vector_store._initialized and vector_store.collection is not None:
            chunks_total = vector_store.collection.count()
            embeddings_total = chunks_total  # 每个 chunk 对应一个 embedding
    except Exception:
        pass

    # 7. 系统监控
    system_metrics = get_system_metrics()

    logger.info(f"Dashboard queried by admin {current_user.username} (id={current_user.id})")

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "disabled": disabled_users,
            "root_count": root_count,
            "admin_count": admin_count,
        },
        "online": {
            "online_users": online_users,
        },
        "knowledge": {
            "total": knowledge_total,
        },
        "documents": {
            "total": documents_total,
        },
        "chunks": {
            "total": chunks_total,
        },
        "embeddings": {
            "total": embeddings_total,
            "available": chunks_total > 0,
        },
        "usage": {
            "today_requests": today_requests,
            "today_prompt_tokens": today_prompt_tokens,
            "today_completion_tokens": today_completion_tokens,
            "today_total_tokens": today_total_tokens,
            "today_cost": 0.0,  # TODO: 实现成本计算
        },
        "system": system_metrics,
    }


@router.get("/dashboard/overview", response_model=DashboardOverviewResponse, summary="Dashboard Overview")
async def get_dashboard_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:view")),
):
    """获取 Dashboard Overview 统计（需要 dashboard:view 权限）。"""
    # Users count
    users_result = await db.execute(select(func.count(User.id)).where(User.deleted_at.is_(None)))
    users_count = users_result.scalar() or 0

    # Knowledge bases count
    kb_result = await db.execute(select(func.count(KnowledgeBase.id)))
    knowledge_bases_count = kb_result.scalar() or 0

    # Documents count
    doc_result = await db.execute(select(func.count(Document.id)))
    documents_count = doc_result.scalar() or 0

    # Conversations count
    conv_result = await db.execute(select(func.count(Conversation.id)))
    conversations_count = conv_result.scalar() or 0

    # Messages count
    msg_result = await db.execute(select(func.count(Message.id)))
    messages_count = msg_result.scalar() or 0

    return DashboardOverviewResponse(
        users_count=users_count,
        knowledge_bases_count=knowledge_bases_count,
        documents_count=documents_count,
        conversations_count=conversations_count,
        messages_count=messages_count,
    )


@router.get("/dashboard/system", response_model=SystemMonitorResponse, summary="System Monitor Status")
async def get_system_monitor(
    current_user: User = Depends(require_permission("dashboard:view")),
):
    """获取系统监控状态（需要 dashboard:view 权限）。"""
    metrics = get_system_metrics()

    # 计算运行时间（简化版）
    uptime = None
    try:
        import psutil
        boot_time = psutil.boot_time()
        uptime_seconds = datetime.now(timezone.utc).timestamp() - boot_time
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        uptime = f"{days}天 {hours}小时 {minutes}分钟"
    except Exception:
        pass

    # 获取 Python 版本和平台
    import platform
    import sys
    python_version = f"Python {sys.version.split()[0]}"
    platform_info = platform.platform()

    return SystemMonitorResponse(
        cpu_usage=metrics.get("cpu_usage"),
        memory_usage=metrics.get("memory_usage"),
        disk_usage=metrics.get("disk_usage"),
        uptime=uptime,
        python_version=python_version,
        platform=platform_info,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
