from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ...core.permissions import require_root, require_permission
from ...models.user import User
from ...schemas.admin_user import AdminUserResponse
from ...services.audit_service import create_audit_log
from ...services.auth.token_service import revoke_user_tokens
from ...services.user_service import update_user_activity
from ...storage.database import get_db

router = APIRouter(prefix="/api/admin/users", tags=["管理员-用户管理"])


# ---------- Helpers ----------

def active_user_filter():
    """返回 SQL 过滤条件：非软删除的用户（deleted_at IS NULL）。
    
    供外部模块（如 auth.py）导入使用，确保所有正常查询默认过滤已删除用户。
    """
    return User.deleted_at.is_(None)


# ---------- Response / Request schemas ----------

class UserOnlineItem(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    last_activity_at: str | None = None
    online: bool = False


class UserStatusUpdateRequest(BaseModel):
    is_active: bool


class UserStatusUpdateResponse(BaseModel):
    id: int
    username: str
    is_active: bool
    message: str


class UserRoleUpdateRequest(BaseModel):
    role: str


class UserRoleUpdateResponse(BaseModel):
    id: int
    username: str
    role: str
    message: str


class UserDeleteResponse(BaseModel):
    id: int
    username: str
    message: str


# ---------- Endpoints ----------

@router.get("/online", response_model=list[UserOnlineItem], summary="获取用户在线状态")
async def list_online_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:view")),
):
    """获取所有用户的在线状态（需要 user:view 权限）。
    
    在线判断：最近 5 分钟内有活动记录。
    """
    now = datetime.now(timezone.utc)
    threshold = 5 * 60  # 5 分钟（秒）

    result = await db.execute(
        select(User).where(active_user_filter()).order_by(User.id)
    )
    users = result.scalars().all()

    items = []
    for u in users:
        online = False
        if u.last_activity_at is not None:
            delta = (now - u.last_activity_at).total_seconds()
            online = delta <= threshold

        items.append(UserOnlineItem(
            id=u.id,
            username=u.username,
            role=u.role,
            is_active=u.is_active,
            last_activity_at=u.last_activity_at.isoformat() if u.last_activity_at else None,
            online=online,
        ))

    return items


@router.get("", response_model=list[AdminUserResponse], summary="获取用户列表")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:view")),
):
    """获取所有正常用户列表（需要 user:view 权限，排除已软删除用户）。"""
    result = await db.execute(
        select(User).where(active_user_filter()).order_by(User.id)
    )
    users = result.scalars().all()
    return [AdminUserResponse(**u.to_dict()) for u in users]


@router.get("/{user_id}", response_model=AdminUserResponse, summary="获取用户详情")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:view")),
):
    """获取指定用户详情（需要 user:view 权限）。"""
    result = await db.execute(
        select(User).where(User.id == user_id, active_user_filter())
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    return AdminUserResponse(**user.to_dict())


@router.patch("/{user_id}/status", response_model=UserStatusUpdateResponse, summary="启用/禁用用户")
async def update_user_status(
    user_id: int,
    request: UserStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:manage")),
):
    """启用或禁用指定用户（需要 user:manage 权限）。"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能修改自身状态",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, active_user_filter())
    )
    target_user = result.scalar_one_or_none()

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    target_user.is_active = request.is_active
    await db.commit()
    await db.refresh(target_user)

    # 禁用用户时撤销其所有活跃 token
    if not request.is_active:
        revoked_count = await revoke_user_tokens(db, target_user.id, reason="admin_disable")
        logger.info(
            f"Admin {current_user.username} disabled user {target_user.username}"
            f" (id={user_id}), revoked {revoked_count} sessions"
        )

    action = "启用" if request.is_active else "禁用"
    audit_action = "ENABLE_USER" if request.is_active else "DISABLE_USER"
    logger.info(f"Admin {current_user.username} {action} user {target_user.username} (id={user_id})")

    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action=audit_action,
        target_type="user",
        target_id=target_user.id,
        detail={"before": not request.is_active, "after": request.is_active},
    )

    return UserStatusUpdateResponse(
        id=target_user.id,
        username=target_user.username,
        is_active=target_user.is_active,
        message=f"用户 {target_user.username} 已{action}",
    )


@router.patch("/{user_id}/role", response_model=UserRoleUpdateResponse, summary="修改用户角色")
async def update_user_role(
    user_id: int,
    request: UserRoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:manage")),
):
    """修改用户角色（需要 user:manage 权限，禁止修改自身角色）。"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能修改自身角色",
        )

    # 校验角色值是否合法
    valid_roles = {"ROOT", "ADMIN", "USER"}
    if request.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效角色，仅支持: {', '.join(sorted(valid_roles))}",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, active_user_filter())
    )
    target_user = result.scalar_one_or_none()

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    old_role = target_user.role
    target_user.role = request.role
    await db.commit()
    await db.refresh(target_user)

    logger.info(f"Admin {current_user.username} changed role of user {target_user.username} (id={user_id}): {old_role} -> {request.role}")

    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="CHANGE_ROLE",
        target_type="user",
        target_id=target_user.id,
        detail={"before": old_role, "after": request.role},
    )

    return UserRoleUpdateResponse(
        id=target_user.id,
        username=target_user.username,
        role=target_user.role,
        message=f"用户 {target_user.username} 角色已从 {old_role} 变更为 {request.role}",
    )


@router.delete("/{user_id}", response_model=UserDeleteResponse, summary="删除用户（软删除）")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user:manage")),
):
    """软删除指定用户（需要 user:manage 权限，设置 deleted_at 而非物理删除）。"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自身账户",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, active_user_filter())
    )
    target_user = result.scalar_one_or_none()

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 软删除：设置 deleted_at 时间戳
    target_user.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(target_user)

    logger.info(f"Admin {current_user.username} soft-deleted user {target_user.username} (id={user_id})")

    await create_audit_log(
        db=db,
        operator_id=current_user.id,
        action="DELETE_USER",
        target_type="user",
        target_id=target_user.id,
        detail={"deleted_at": target_user.deleted_at.isoformat() if target_user.deleted_at else None},
    )

    return UserDeleteResponse(
        id=target_user.id,
        username=target_user.username,
        message=f"用户 {target_user.username} 已被删除",
    )