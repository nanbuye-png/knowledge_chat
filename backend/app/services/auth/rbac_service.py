"""RBAC 权限服务（角色 / 权限码查询与分配）。

现状与边界（审计 §6.3）
-----------------------
* ``has_permission`` / ``has_role`` 是管理后台 ``require_permission`` /
  ``require_role`` 依赖的唯一实现，join 链条必须完整（§6.3-1）。
* ``user_roles``（用户 ↔ 角色）**目前没有生产写入路径**：只有
  :meth:`RBACService.assign_role` 会写它，而该方法只被测试调用；
  实际生效的角色始终是 ``users.role`` 单字段。因此细粒度权限码
  （permissions / role_permissions）目前只对「按 name 匹配的默认角色」生效，
  即 **Planned**，不是已上线能力 —— 不要在业务代码里假设多角色可用。
* ``check_default_roles`` / ``init_default_roles`` 在启动时幂等初始化
  roles / permissions / role_permissions，是权限码得以生效的前提。
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from loguru import logger

from ...models.user import User
from ...models.permission import Role, Permission, user_roles, role_permissions
from ...core.rbac import UserRole


# ``users.role``（历史单角色字段）→ RBAC 角色名（roles.name）的映射。
# 默认 RBAC 角色集是 ROOT / ADMIN / MEMBER / VIEWER，没有名为 USER 的角色；
# 普通用户在权限表里对应 MEMBER（dashboard:view + knowledge:view）。
# 审计 §6.3-2：user_roles 没有生产写入路径，因此这条映射是细粒度权限码
# "真的生效"的唯一通道；将来启用多角色（Planned）后它仍作为兜底保留。
LEGACY_ROLE_TO_RBAC_ROLE: dict[str, str] = {
    UserRole.USER.value: "MEMBER",
}


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
        
        # 向后兼容：检查 user.role 字段。默认 RBAC 角色名与 users.role 同名
        # （ROOT / ADMIN），USER 需要映射到 MEMBER（见 LEGACY_ROLE_TO_RBAC_ROLE）。
        if role_name in (user.role, LEGACY_ROLE_TO_RBAC_ROLE.get(user.role, user.role)):
            return True
        
        # 检查 RBAC 角色（显式 join 链，Role 必须真的进入 FROM）
        role_result = await db.execute(
            select(Role)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(
                user_roles.c.user_id == user_id,
                Role.name == role_name,
            )
            .limit(1)  # user_roles 主键 (user_id, role_id) 已保证唯一，limit 是兜底
        )
        return role_result.first() is not None

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
        #
        # 审计 §6.3-1（P0）：原写法只把 Role 写进 ON 条件
        #   .join(role_permissions, Permission.id == role_permissions.c.permission_id)
        #   .join(user_roles, Role.id == user_roles.c.role_id)
        # 生成的 SQL 里 roles **没有进入 FROM**（"... JOIN user_roles ON
        # roles.id = user_roles.role_id"），SQLite 直接报 "no such column:
        # roles.id" —— 于是所有 require_permission 的管理后台接口一律 500。
        if await RBACService._has_permission_via_user_roles(db, user_id, permission_code):
            return True

        # 兼容路径（审计 §6.3-2）：user_roles 目前没有生产写入路径（见模块
        # docstring，状态 Planned），真正生效的一直是 users.role 单字段。
        # 所以还要按"单角色 → 同名 RBAC 角色"再查一次；否则修完 join，ADMIN
        # 依旧拿不到 user:view，管理后台还是进不去（实测）。
        rbac_role_name = LEGACY_ROLE_TO_RBAC_ROLE.get(user.role, user.role)
        return await RBACService._role_name_has_permission(
            db, rbac_role_name, permission_code
        )

    @staticmethod
    async def _has_permission_via_user_roles(
        db: AsyncSession, user_id: int, permission_code: str
    ) -> bool:
        """多角色（user_roles）路径：Permission ← role_permissions ← roles ← user_roles。"""
        stmt = (
            select(Permission.id)
            .join(role_permissions, Permission.id == role_permissions.c.permission_id)
            .join(Role, Role.id == role_permissions.c.role_id)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(
                user_roles.c.user_id == user_id,
                Permission.code == permission_code,
            )
            .limit(1)  # 多角色权限重叠时只取一行：避免 MultipleResultsFound → 500
        )
        return (await db.execute(stmt)).first() is not None

    @staticmethod
    async def _role_name_has_permission(
        db: AsyncSession, role_name: str, permission_code: str
    ) -> bool:
        """单角色路径：roles.name → role_permissions → permissions。"""
        stmt = (
            select(Permission.id)
            .join(role_permissions, Permission.id == role_permissions.c.permission_id)
            .join(Role, Role.id == role_permissions.c.role_id)
            .where(
                Role.name == role_name,
                Permission.code == permission_code,
            )
            .limit(1)
        )
        return (await db.execute(stmt)).first() is not None

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