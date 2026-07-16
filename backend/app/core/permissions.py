from fastapi import Depends, HTTPException, status

from ..auth.deps import get_current_user
from ..models.user import User
from ..services.auth.rbac_service import RBACService
from .rbac import UserRole
from sqlalchemy.ext.asyncio import AsyncSession
from ..storage.database import get_db


async def require_authenticated(
    current_user: User = Depends(get_current_user),
) -> User:
    """要求用户已认证。

    与 get_current_user 行为一致，提供统一的依赖入口。
    """
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """要求当前用户为 ADMIN 或以上角色。"""
    if current_user.role not in (UserRole.ADMIN, UserRole.ROOT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


async def require_root(
    current_user: User = Depends(get_current_user),
) -> User:
    """要求当前用户为 ROOT 角色。"""
    if current_user.role != UserRole.ROOT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要 ROOT 权限",
        )
    return current_user


async def require_admin_or_root(
    current_user: User = Depends(get_current_user),
) -> User:
    """要求当前用户为 ADMIN 或 ROOT 角色。"""
    if current_user.role not in (UserRole.ADMIN, UserRole.ROOT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员或更高权限",
        )
    return current_user


def require_role(role_name: str):
    """要求用户拥有指定角色的依赖工厂函数。
    
    Args:
        role_name: 角色名称（如 "ROOT", "ADMIN"）
        
    Returns:
        FastAPI 依赖函数
        
    Example:
        @router.get("/admin", dependencies=[Depends(require_role("ADMIN"))])
        async def admin_endpoint():
            pass
    """
    async def _check_role(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        has_role = await RBACService.has_role(current_user.id, role_name, db)
        if not has_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要 {role_name} 角色权限",
            )
        return current_user
    
    return _check_role


def require_permission(permission_code: str):
    """要求用户拥有指定权限的依赖工厂函数。
    
    Args:
        permission_code: 权限代码（如 "dashboard:view", "user:manage"）
        
    Returns:
        FastAPI 依赖函数
        
    Example:
        @router.get("/dashboard", dependencies=[Depends(require_permission("dashboard:view"))])
        async def view_dashboard():
            pass
    """
    async def _check_permission(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        has_perm = await RBACService.has_permission(current_user.id, permission_code, db)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要权限: {permission_code}",
            )
        return current_user
    
    return _check_permission
