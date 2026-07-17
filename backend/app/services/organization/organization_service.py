"""Organization CRUD service."""
from typing import Optional

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.organization import Organization, OrganizationMember
from ...models.user import User
from ...schemas.organization import OrganizationCreate, OrganizationUpdate


class OrganizationService:
    """组织 CRUD 服务。"""

    @staticmethod
    async def create(db: AsyncSession, data: OrganizationCreate, owner_id: int) -> Organization:
        """创建组织并添加创建者为 OWNER。"""
        org = Organization(
            name=data.name,
            slug=data.slug,
            description=data.description,
        )
        db.add(org)
        await db.flush()

        # 添加创建者为 OWNER
        member = OrganizationMember(
            organization_id=org.id,
            user_id=owner_id,
            role="OWNER",
        )
        db.add(member)
        await db.commit()
        await db.refresh(org)
        logger.info(f"组织创建成功: {org.slug} (owner={owner_id})")
        return org

    @staticmethod
    async def get(db: AsyncSession, org_id: int) -> Optional[Organization]:
        """获取组织详情。"""
        result = await db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Organization]:
        """通过 slug 获取组织。"""
        result = await db.execute(
            select(Organization).where(Organization.slug == slug)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None,
    ) -> tuple[list[Organization], int]:
        """组织列表。支持按用户过滤（用户所属组织）。"""
        query = select(Organization)
        count_query = select(func.count(Organization.id))

        if user_id is not None:
            # 只返回用户所属的组织
            subq = select(OrganizationMember.organization_id).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active == True,
            )
            query = query.where(Organization.id.in_(subq))
            count_query = count_query.where(Organization.id.in_(subq))

        # 总计数
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        result = await db.execute(
            query.order_by(Organization.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = list(result.scalars().all())
        return items, total

    @staticmethod
    async def update(db: AsyncSession, org_id: int, data: OrganizationUpdate) -> Optional[Organization]:
        """更新组织。"""
        org = await OrganizationService.get(db, org_id)
        if not org:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(org, field, value)

        await db.commit()
        await db.refresh(org)
        logger.info(f"组织更新成功: {org.slug}")
        return org

    @staticmethod
    async def delete(db: AsyncSession, org_id: int) -> bool:
        """删除组织。"""
        org = await OrganizationService.get(db, org_id)
        if not org:
            return False

        await db.delete(org)
        await db.commit()
        logger.info(f"组织删除成功: id={org_id}")
        return True

    @staticmethod
    async def get_user_role(db: AsyncSession, org_id: int, user_id: int) -> Optional[str]:
        """获取用户在组织中的角色。"""
        result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active == True,
            )
        )
        member = result.scalar_one_or_none()
        return member.role if member else None