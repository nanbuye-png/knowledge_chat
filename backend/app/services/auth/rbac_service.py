from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from loguru import logger

from ...models.user import User
from ...models.permission import Role, Permission, user_roles, role_permissions
from ...core.rbac import UserRole


class RBACService:
    """RBAC 权限服务。"""

    @staticmethod
    async def has_role(user_id: int, role_name: str, db: AsyncSession) -> bool:
        """检查用户是否拥有指定角色。
        
        Args:
            user_id: 用户 ID
            role_name: 角色名称
            db: 数据库会话
            
        Returns:
            是否拥有该角色
        """
        # 检查用户的 role 字段（向后兼容）
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return False
        
        # 向后兼容：检查 user.role 字段
        if user.role == role_name:
            return True
        
        # 检查 RBAC 角色
        role_result = await db.execute(
            select(Role)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(
                user_roles.c.user_id == user_id,
                Role.name == role_name
            )
        )
        return role_result.scalar_one_or_none() is not None

    @staticmethod
    async def has_permission(user_id: int, permission_code: str, db: AsyncSession) -> bool:
        """检查用户是否拥有指定权限。
        
        Args:
            user_id: 用户 ID
            permission_code: 权限代码
            db: 数据库会话
            
        Returns:
            是否拥有该权限
        """
        # 检查用户的 role 字段（向后兼容）
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return False
        
        # ROOT 用户拥有所有权限
        if user.role == UserRole.ROOT:
            return True
        
        # 检查 RBAC 权限
        result = await db.execute(
            select(Permission)
            .join(role_permissions, Permission.id == role_permissions.c.permission_id)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(
                user_roles.c.user_id == user_id,
                Permission.code == permission_code
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def assign_role(user_id: int, role_name: str, db: AsyncSession) -> bool:
        """为用户分配角色。
        
        Args:
            user_id: 用户 ID
            role_name: 角色名称
            db: 数据库会话
            
        Returns:
            是否分配成功
        """
        # 查找角色
        role_result = await db.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one_or_none()
        if not role:
            logger.warning(f"Role not found: {role_name}")
            return False
        
        # 检查是否已分配
        existing = await db.execute(
            select(user_roles).where(
                user_roles.c.user_id == user_id,
                user_roles.c.role_id == role.id
            )
        )
        if existing.scalar_one_or_none():
            return True
        
        # 分配角色
        await db.execute(
            user_roles.insert().values(user_id=user_id, role_id=role.id)
        )
        await db.commit()
        return True

    @staticmethod
    async def init_default_roles(db: AsyncSession) -> None:
        """初始化默认角色和权限。"""
        try:
            # 创建默认角色
            roles_data = [
                ("ROOT", "超级管理员，拥有所有权限"),
                ("ADMIN", "管理员，拥有部分管理权限"),
                ("MEMBER", "普通会员"),
                ("VIEWER", "访客，只读权限"),
            ]
            
            for role_name, description in roles_data:
                existing = await db.execute(select(Role).where(Role.name == role_name))
                if not existing.scalar_one_or_none():
                    role = Role(name=role_name, description=description)
                    db.add(role)
            
            await db.flush()
            
            # 创建默认权限
            permissions_data = [
                ("Dashboard 查看", "dashboard:view", "查看系统概览和监控数据"),
                ("Dashboard 管理", "dashboard:manage", "管理系统设置"),
                ("用户查看", "user:view", "查看用户列表"),
                ("用户管理", "user:manage", "创建、编辑、删除用户"),
                ("知识库查看", "knowledge:view", "查看知识库"),
                ("知识库管理", "knowledge:manage", "创建、编辑、删除知识库"),
                ("Prompt 管理", "prompt:manage", "管理 Prompt 模板"),
            ]
            
            for name, code, description in permissions_data:
                existing = await db.execute(select(Permission).where(Permission.code == code))
                if not existing.scalar_one_or_none():
                    permission = Permission(name=name, code=code, description=description)
                    db.add(permission)
            
            await db.flush()
            
            # 获取角色和权限
            root_role = (await db.execute(select(Role).where(Role.name == "ROOT"))).scalar_one_or_none()
            admin_role = (await db.execute(select(Role).where(Role.name == "ADMIN"))).scalar_one_or_none()
            member_role = (await db.execute(select(Role).where(Role.name == "MEMBER"))).scalar_one_or_none()
            viewer_role = (await db.execute(select(Role).where(Role.name == "VIEWER"))).scalar_one_or_none()
            
            all_permissions = (await db.execute(select(Permission))).scalars().all()
            permission_map = {p.code: p for p in all_permissions}
            
            # ROOT: 所有权限
            if root_role:
                for perm in all_permissions:
                    existing = await db.execute(
                        select(role_permissions).where(
                            role_permissions.c.role_id == root_role.id,
                            role_permissions.c.permission_id == perm.id,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        await db.execute(
                            role_permissions.insert().values(role_id=root_role.id, permission_id=perm.id)
                        )
            
            # ADMIN: dashboard:view, user:view, user:manage, knowledge:view, knowledge:manage
            if admin_role:
                admin_perms = ["dashboard:view", "user:view", "user:manage", "knowledge:view", "knowledge:manage"]
                for code in admin_perms:
                    perm = permission_map.get(code)
                    if perm:
                        existing = await db.execute(
                            select(role_permissions).where(
                                role_permissions.c.role_id == admin_role.id,
                                role_permissions.c.permission_id == perm.id,
                            )
                        )
                        if not existing.scalar_one_or_none():
                            await db.execute(
                                role_permissions.insert().values(role_id=admin_role.id, permission_id=perm.id)
                            )
            
            # MEMBER: dashboard:view, knowledge:view
            if member_role:
                member_perms = ["dashboard:view", "knowledge:view"]
                for code in member_perms:
                    perm = permission_map.get(code)
                    if perm:
                        existing = await db.execute(
                            select(role_permissions).where(
                                role_permissions.c.role_id == member_role.id,
                                role_permissions.c.permission_id == perm.id,
                            )
                        )
                        if not existing.scalar_one_or_none():
                            await db.execute(
                                role_permissions.insert().values(role_id=member_role.id, permission_id=perm.id)
                            )
            
            # VIEWER: dashboard:view
            if viewer_role:
                viewer_perms = ["dashboard:view"]
                for code in viewer_perms:
                    perm = permission_map.get(code)
                    if perm:
                        existing = await db.execute(
                            select(role_permissions).where(
                                role_permissions.c.role_id == viewer_role.id,
                                role_permissions.c.permission_id == perm.id,
                            )
                        )
                        if not existing.scalar_one_or_none():
                            await db.execute(
                                role_permissions.insert().values(role_id=viewer_role.id, permission_id=perm.id)
                            )
            
            await db.commit()
            logger.info("✅ RBAC default roles and permissions initialized")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to initialize RBAC: {e}")
            raise