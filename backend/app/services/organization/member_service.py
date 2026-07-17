"""Organization member management service."""
from typing import Optional

from loguru import logger
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.organization import OrganizationMember
from ...models.user import User


class OrganizationMemberService:
    """组织成员管理服务。"""

    ALLOWED_ROLES = {"OWNER", "ADMIN", "MEMBER"}

    @staticmethod
    async def add_member(
        db: AsyncSession,
        organization_id: int,
        user_id: int,
        role: str = "MEMBER",
    ) -> Optional[OrganizationMember]:
        """添加成员到组织。"""
        if role not in OrganizationMemberService.ALLOWED_ROLES:
            raise ValueError(f"无效角色: {role}，允许: {OrganizationMemberService.ALLOWED_ROLES}")

        # 检查是否已存在
        existing = await OrganizationMemberService.get_member(db, organization_id, user_id)
        if existing:
            if existing.is_active:
                raise ValueError("用户已是该组织成员")
            # 重新激活
            existing.is_active = True
            existing.role = role
            await db.commit()
            await db.refresh(existing)
            return existing

        member = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
        )
        db.add(member)
        await db.commit()
        await db.refresh(member)
        logger.info(f"成员添加: org={organization_id}, user={user_id}, role={role}")
        return member

    @staticmethod
    async def remove_member(db: AsyncSession, organization_id: int, user_id: int) -> bool:
        """从组织移除成员（软删除）。"""
        member = await OrganizationMemberService.get_member(db, organization_id, user_id)
        if not member or not member.is_active:
            return False

        member.is_active = False
        await db.commit()
        logger.info(f"成员移除: org={organization_id}, user={user_id}")
        return True

    @staticmethod
    async def update_role(db: AsyncSession, organization_id: int, user_id: int, new_role: str) -> Optional[OrganizationMember]:
        """更新成员角色。"""
        if new_role not in OrganizationMemberService.ALLOWED_ROLES:
            raise ValueError(f"无效角色: {new_role}")

        member = await OrganizationMemberService.get_member(db, organization_id, user_id)
        if not member or not member.is_active:
            return None

        member.role = new_role
        await db.commit()
        await db.refresh(member)
        logger.info(f"成员角色更新: org={organization_id}, user={user_id}, role={new_role}")
        return member

    @staticmethod
    async def get_member(db: AsyncSession, organization_id: int, user_id: int) -> Optional[OrganizationMember]:
        """获取成员关系。"""
        result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_members(
        db: AsyncSession,
        organization_id: int,
        skip: int = 0,
        limit: int = 50,
        only_active: bool = True,
    ) -> tuple[list[OrganizationMember], int]:
        """成员列表。"""
        query = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
        )
        count_query = select(func.count(OrganizationMember.id)).where(
            OrganizationMember.organization_id == organization_id,
        )

        if only_active:
            query = query.where(OrganizationMember.is_active == True)
            count_query = count_query.where(OrganizationMember.is_active == True)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        result = await db.execute(
            query.order_by(OrganizationMember.joined_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = list(result.scalars().all())
        return items, total

    @staticmethod
    async def get_user_organizations(db: AsyncSession, user_id: int) -> list[OrganizationMember]:
        """获取用户所属的所有组织。"""
        result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active == True,
            )
        )
        return list(result.scalars().all())