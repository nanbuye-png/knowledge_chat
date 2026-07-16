import datetime

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ...core.permissions import require_root, require_permission
from ...models.user import User
from ...models.user_session import UserSession
from ...services.audit_service import create_audit_log
from ...services.session_service import revoke_session
from ...storage.database import get_db

router = APIRouter(prefix="/api/admin/sessions", tags=["管理员-Session管理"])


class AdminSessionResponse(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    device_info: str | None = None
    ip_address: str | None = None
    created_at: str | None = None
    last_used_at: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    is_active: bool = False


@router.get("", response_model=list[AdminSessionResponse], summary="获取所有用户 Session")
async def list_all_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:view")),
):
    """获取所有用户 Session（需要 user:view 权限）。"""
    result = await db.execute(
        select(UserSession).order_by(UserSession.created_at.desc()).limit(100)
    )
    sessions = result.scalars().all()

    # 批量查询用户信息
    user_ids = list(set(s.user_id for s in sessions))
    users_result = await db.execute(
        select(User.id, User.username).where(User.id.in_(user_ids))
    )
    user_map = {row[0]: row[1] for row in users_result.fetchall()}

    return [
        AdminSessionResponse(
            id=s.id,
            user_id=s.user_id,
            username=user_map.get(s.user_id),
            device_info=s.device_info,
            ip_address=s.ip_address,
            created_at=s.created_at.isoformat() if s.created_at else None,
            last_used_at=s.last_used_at.isoformat() if s.last_used_at else None,
            expires_at=s.expires_at.isoformat() if s.expires_at else None,
            revoked_at=s.revoked_at.isoformat() if s.revoked_at else None,
            is_active=s.revoked_at is None and s.expires_at > datetime.now(timezone.utc),
        )
        for s in sessions
    ]


@router.delete("/{session_id}", summary="强制注销 Session")
async def revoke_session_endpoint(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:manage")),
):
    """强制注销指定 Session（需要 user:manage 权限）。"""
    result = await db.execute(
        select(UserSession).where(UserSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session 不存在",
        )

    if session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session 已被注销",
        )

    await revoke_session(db, session_id)

    # 记录审计日志
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="REVOKE_SESSION",
        target_type="session",
        target_id=session_id,
        detail={"user_id": session.user_id, "session_id": session_id},
    )

    logger.info(f"Admin {current_user.username} revoked session {session_id} (user_id={session.user_id})")

    return {"message": "Session 已注销"}