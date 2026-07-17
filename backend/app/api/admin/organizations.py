"""Organization CRUD API."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ...core.permissions import require_admin_or_root, require_root
from ...models.user import User
from ...schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationListResponse,
    OrganizationMemberResponse,
    OrganizationMemberAdd,
    OrganizationMemberUpdateRole,
)
from ...services.organization import OrganizationService, OrganizationMemberService
from ...storage.database import get_db

router = APIRouter(prefix="/api/admin/organizations", tags=["管理员-组织管理"])


# ============================================================
# 组织 CRUD
# ============================================================

@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """创建组织（需要 ADMIN 或 ROOT 权限）。"""
    # 检查 slug 唯一性
    existing = await OrganizationService.get_by_slug(db, data.slug)
    if existing:
        raise HTTPException(status_code=400, detail="组织标识 slug 已存在")

    org = await OrganizationService.create(db, data, current_user.id)
    return OrganizationResponse.model_validate(org)


@router.get("", response_model=OrganizationListResponse)
async def list_organizations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """组织列表。"""
    # ROOT 可见所有，ADMIN 可见自己组织
    user_id = None if current_user.role == "ROOT" else current_user.id
    items, total = await OrganizationService.list(db, skip, limit, user_id)
    return OrganizationListResponse(
        items=[OrganizationResponse.model_validate(o) for o in items],
        total=total,
    )


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """组织详情。"""
    org = await OrganizationService.get(db, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    return OrganizationResponse.model_validate(org)


@router.put("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: int,
    data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """修改组织。"""
    org = await OrganizationService.update(db, org_id, data)
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    return OrganizationResponse.model_validate(org)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """删除组织（仅 ROOT）。"""
    deleted = await OrganizationService.delete(db, org_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="组织不存在")


# ============================================================
# 成员管理
# ============================================================

@router.post("/{org_id}/members", response_model=OrganizationMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    org_id: int,
    data: OrganizationMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """添加成员到组织。"""
    try:
        member = await OrganizationMemberService.add_member(db, org_id, data.user_id, data.role)
        if not member:
            raise HTTPException(status_code=404, detail="组织不存在")
        return OrganizationMemberResponse.model_validate(member)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{org_id}/members", response_model=list[OrganizationMemberResponse])
async def list_members(
    org_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """成员列表。"""
    items, total = await OrganizationMemberService.list_members(db, org_id, skip, limit)
    return [OrganizationMemberResponse.model_validate(m) for m in items]


@router.put("/{org_id}/members/{user_id}", response_model=OrganizationMemberResponse)
async def update_member_role(
    org_id: int,
    user_id: int,
    data: OrganizationMemberUpdateRole,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """修改成员角色。"""
    try:
        member = await OrganizationMemberService.update_role(db, org_id, user_id, data.role)
        if not member:
            raise HTTPException(status_code=404, detail="成员不存在")
        return OrganizationMemberResponse.model_validate(member)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """移除成员。"""
    removed = await OrganizationMemberService.remove_member(db, org_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="成员不存在")