from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..auth.deps import get_current_user
from ..models.user import User
from ..services.session_service import get_user_sessions
from ..storage.database import get_db

router = APIRouter(prefix="/api/auth/sessions", tags=["认证-Session管理"])


class SessionResponse(BaseModel):
    id: int
    device_info: str | None = None
    ip_address: str | None = None
    created_at: str | None = None
    last_used_at: str | None = None
    expires_at: str | None = None
    is_active: bool = False


@router.get("", response_model=list[SessionResponse], summary="获取当前用户的 Session 列表")
async def list_my_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前登录用户的所有 Session。"""
    sessions = await get_user_sessions(db, current_user.id)
    return [SessionResponse(**s.to_dict()) for s in sessions]