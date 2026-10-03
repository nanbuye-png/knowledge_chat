from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..auth.deps import get_current_user, oauth2_scheme
from ..models.user import User
from ..models.user_session import UserSession
from ..services.audit_service import _extract_client_info, create_audit_log
from ..services.session_service import _hash_token, get_user_sessions, revoke_session
from ..storage.database import get_db

router = APIRouter(prefix="/api/auth/sessions", tags=["认证-Session管理"])


class SessionResponse(BaseModel):
    id: int
    device_info: str | None = None
    ip_address: str | None = None
    created_at: str | None = None
    last_used_at: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    is_active: bool = False
    # 审计 §5.15：SessionsPage 一直用 `s.is_current` 决定是否显示 "Current" 徽标，
    # 但后端从来没返回过这个字段 → 徽标永远不出现。
    is_current: bool = False


class RevokeSessionResponse(BaseModel):
    message: str
    session_id: int


@router.get("", response_model=list[SessionResponse], summary="获取当前用户的 Session 列表")
async def list_my_sessions(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """获取当前登录用户的所有 Session。

    响应字段以本文件的 ``SessionResponse`` 为准（审计 §5.15）：前端 SessionsPage
    此前读的是 ``device`` / ``ip`` / ``last_active`` / ``is_current`` 四个**都不存在**
    的字段，所以卡片上永远显示 "Unknown Device"、"IP: --"、时间 "--"，且"当前设备"
    徽标永不出现。现在补齐 ``is_current``（按请求携带的 token 的 SHA256 判定）。
    """
    current_hash = _hash_token(token) if token else None
    sessions = await get_user_sessions(db, current_user.id)
    return [
        SessionResponse(
            **s.to_dict(),
            is_current=current_hash is not None and s.token_hash == current_hash,
        )
        for s in sessions
    ]


@router.delete(
    "/{session_id}",
    response_model=RevokeSessionResponse,
    summary="注销指定设备（Session）",
)
async def revoke_my_session(
    session_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """注销**自己名下**的某个 Session（前端 SessionsPage 的"退出该设备"）。

    与管理员端 ``DELETE /api/admin/sessions/{id}``（``user:manage`` 权限）的区别：

    - 不接受 ``user_id``，目标 Session 必须属于当前用户；不属于时一律 404
      （不泄露他人 Session 是否存在，避免 ID 枚举）；
    - 不允许注销**当前请求所在的** Session —— 那是"退出登录"的语义，走
      ``POST /api/auth/logout``；这里若允许，客户端会带着已失效 token 以为自己
      还登录着，下一个请求直接 401。
    """
    result = await db.execute(select(UserSession).where(UserSession.id == session_id))
    session = result.scalar_one_or_none()

    if session is None or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session 不存在",
        )

    if session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该 Session 已被注销",
        )

    if token and session.token_hash == _hash_token(token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能注销当前设备，请使用退出登录",
        )

    await revoke_session(db, session_id)

    ip, ua = _extract_client_info(request)
    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="REVOKE_SESSION",
        target_type="session",
        target_id=session_id,
        detail={"session_id": session_id, "self_service": True},
        ip_address=ip,
        user_agent=ua,
        status="SUCCESS",
    )

    logger.info(f"User {current_user.username} revoked own session {session_id}")
    return RevokeSessionResponse(message="已退出该设备", session_id=session_id)
