from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ...core.permissions import require_permission
from ...models.user import User
from ...services.audit_service import get_logs
from ...storage.database import get_db

router = APIRouter(prefix="/api/admin/audit-logs", tags=["管理员-审计日志"])


class AuditLogItem(BaseModel):
    id: int
    operator_id: int
    action: str
    target_type: str
    target_id: int | None = None
    detail: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    status: str
    created_at: str | None = None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int


@router.get("", response_model=AuditLogListResponse, summary="获取审计日志（分页）")
async def list_audit_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    action: str | None = Query(None, description="按操作类型过滤"),
    user_id: int | None = Query(None, description="按操作者过滤"),
    target_type: str | None = Query(None, description="按目标类型过滤"),
    status: str | None = Query(None, description="按状态过滤（SUCCESS/FAILURE）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:view")),
):
    """分页查询审计日志（需要 dashboard:view 权限）。"""
    result = await get_logs(
        db=db,
        page=page,
        page_size=page_size,
        action=action,
        user_id=user_id,
        target_type=target_type,
        status=status,
    )
    return AuditLogListResponse(**result)