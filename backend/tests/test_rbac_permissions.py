"""RBAC 权限查询与管理后台可达性测试 —— 审计 §6.3。

审计原文（docs/KNOWLEDGE_CHAT_REALITY_AUDIT.md §6.3）：
    1) [P0] has_permission 的查询 join 缺 roles 表 → ADMIN 访问整个管理后台 500
    2) [死功能] user_roles 表无任何写入方 → 细粒度权限码实际从未启用
    4) [策略不一致] PATCH /users/{id}/role 允许设为 ROOT（admin/users.py:349），
       而创建用户只允许 {USER, ADMIN} → ADMIN 可把任意用户提权为 ROOT

本文件用真实 SQLite 验证：

* ``has_permission`` 的 join 是**显式链条**，不再依赖隐式笛卡尔积；
* 一个用户拥有多个角色且权限重叠时不会炸 MultipleResultsFound（那就是
  "管理后台 500" 的复现条件）；
* 权限只能来自**用户自己的**角色（其他角色授的权限不能白拿）；
* ADMIN 真的能打开管理后台（require_permission("user:view") → 200）；
* 角色变更策略：ADMIN 不能把人提成 ROOT，只有 ROOT 能授予 ROOT。
"""

import asyncio

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("no_rate_limits")

PASSWORD = "Str0ng!Passw0rd123"


# ---------------------------------------------------------------------------
# 数据准备
# ---------------------------------------------------------------------------


def _seed_rbac(temp_db) -> None:
    """初始化默认角色权限（等价于应用启动时的 RBACService.init_default_roles）。"""
    from app.services.auth.rbac_service import RBACService

    async def _run():
        async with temp_db.session() as session:
            await RBACService.init_default_roles(session)

    asyncio.run(_run())


def _add_user(temp_db, username: str, role: str) -> int:
    """直插一个用户并返回 id（不走注册接口，避免密码策略干扰专注点）。"""
    from app.auth.security import hash_password
    from app.models.user import User

    async def _run() -> int:
        async with temp_db.session() as session:
            user = User(
                username=username,
                email=f"{username}@example.com",
                password_hash=hash_password(PASSWORD),
                role=role,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user.id

    return asyncio.run(_run())


def _has_permission(temp_db, user_id: int, code: str) -> bool:
    from app.services.auth.rbac_service import RBACService

    async def _run() -> bool:
        async with temp_db.session() as session:
            return await RBACService.has_permission(user_id, code, session)

    return asyncio.run(_run())


def _assign_role(temp_db, user_id: int, role_name: str) -> bool:
    from app.services.auth.rbac_service import RBACService

    async def _run() -> bool:
        async with temp_db.session() as session:
            return await RBACService.assign_role(user_id, role_name, session)

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# 1：权限查询本身
# ---------------------------------------------------------------------------


class TestHasPermissionQuery:
    def test_admin_gets_dashboard_view_from_its_role(self, temp_db):
        """ADMIN 的 dashboard:view 必须来自 role_permissions。"""
        _seed_rbac(temp_db)
        admin_id = _add_user(temp_db, "rbac_admin", "ADMIN")

        assert _has_permission(temp_db, admin_id, "dashboard:view") is True
        print("[PASS] ADMIN 通过 role_permissions 拿到 dashboard:view")

    def test_plain_user_does_not_get_user_manage(self, temp_db):
        _seed_rbac(temp_db)
        user_id = _add_user(temp_db, "rbac_user", "USER")

        assert _has_permission(temp_db, user_id, "user:manage") is False
        assert _has_permission(temp_db, user_id, "dashboard:view") is True
        print("[PASS] USER 无 user:manage、有 dashboard:view")

    def test_root_bypasses_permission_lookup(self, temp_db):
        """ROOT 不查权限表：直接放行（任何权限码都要能过）。"""
        _seed_rbac(temp_db)
        root_id = _add_user(temp_db, "rbac_root", "ROOT")

        assert _has_permission(temp_db, root_id, "不存在的权限码") is True
        print("[PASS] ROOT 直接放行（含不存在的权限码）")

    def test_overlapping_roles_do_not_raise_multiple_results(self, temp_db):
        """同时拥有 ADMIN 与 MEMBER 两个角色（都有 dashboard:view）也不能 500。

        审计 §6.3-1 的"ADMIN 访问管理后台 500"根因：查询用
        ``scalar_one_or_none()`` 配隐式笛卡尔积 join，多行结果直接抛
        MultipleResultsFound。
        """
        _seed_rbac(temp_db)
        user_id = _add_user(temp_db, "rbac_multi", "USER")
        assert _assign_role(temp_db, user_id, "ADMIN") is True
        assert _assign_role(temp_db, user_id, "MEMBER") is True

        assert _has_permission(temp_db, user_id, "dashboard:view") is True
        print("[PASS] 多角色权限重叠不再抛 MultipleResultsFound")

    def test_permission_does_not_leak_from_other_roles(self, temp_db):
        """权限必须来自用户自己的角色：VIEWER 的权限不能被 USER 蹭到。"""
        from app.models.permission import Permission, Role, role_permissions

        _seed_rbac(temp_db)
        user_id = _add_user(temp_db, "rbac_viewer_owner", "USER")

        async def _grant_viewer_only():
            async with temp_db.session() as session:
                viewer = (
                    await session.execute(select(Role).where(Role.name == "VIEWER"))
                ).scalar_one()
                perm = Permission(name="专属权限", code="secret:view")
                session.add(perm)
                await session.commit()
                await session.refresh(perm)
                await session.execute(
                    role_permissions.insert().values(
                        role_id=viewer.id, permission_id=perm.id
                    )
                )
                await session.commit()

        asyncio.run(_grant_viewer_only())
        assert _has_permission(temp_db, user_id, "secret:view") is False
        print("[PASS] 其他角色授予的权限不会泄漏给当前用户")


# ---------------------------------------------------------------------------
# 2：管理后台真的能打开（端到端）
# ---------------------------------------------------------------------------


def _login(client, username: str) -> dict:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestAdminBackendReachability:
    def test_admin_can_list_users(self, client, temp_db):
        """审计 §6.3-1 端到端：ADMIN 调 require_permission("user:view") 必须 200。"""
        _seed_rbac(temp_db)
        _add_user(temp_db, "admin_backend", "ADMIN")
        _add_user(temp_db, "normal_user", "USER")

        headers = _login(client, "admin_backend")
        resp = client.get("/api/admin/users", headers=headers)
        assert resp.status_code == 200, resp.text
        print("[PASS] ADMIN 访问 /api/admin/users → 200（此前 500）")

    def test_user_is_forbidden_on_admin_backend(self, client, temp_db):
        _seed_rbac(temp_db)
        _add_user(temp_db, "plain_denied", "USER")

        headers = _login(client, "plain_denied")
        resp = client.get("/api/admin/users", headers=headers)
        assert resp.status_code == 403, resp.text
        print("[PASS] 普通用户访问管理后台 → 403")


# ---------------------------------------------------------------------------
# 3：角色变更策略（审计 §6.3-4）
# ---------------------------------------------------------------------------


def _set_role(client, headers, user_id: int, role: str):
    return client.patch(
        f"/api/admin/users/{user_id}/role", json={"role": role}, headers=headers
    )


class TestRoleEscalationPolicy:
    def test_admin_cannot_promote_to_root(self, client, temp_db):
        """ADMIN 把别人提成 ROOT = 自我提权（他能再切回自己）→ 必须拒绝。"""
        _seed_rbac(temp_db)
        _add_user(temp_db, "escalator", "ADMIN")
        victim_id = _add_user(temp_db, "promotion_target", "USER")

        headers = _login(client, "escalator")
        resp = _set_role(client, headers, victim_id, "ROOT")
        assert resp.status_code == 403, resp.text
        print("[PASS] ADMIN → ROOT 提权被拒（403）")

    def test_admin_can_promote_to_admin(self, client, temp_db):
        """ADMIN 之间互授是既有策略（创建用户就允许 {USER, ADMIN}），不能被误伤。"""
        _seed_rbac(temp_db)
        _add_user(temp_db, "granter", "ADMIN")
        target_id = _add_user(temp_db, "admin_target", "USER")

        headers = _login(client, "granter")
        resp = _set_role(client, headers, target_id, "ADMIN")
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "ADMIN"
        print("[PASS] ADMIN 可授予 ADMIN")

    def test_root_can_promote_to_root(self, client, temp_db):
        """ROOT 是唯一能授予 ROOT 的角色（否则 ROOT 无法交接）。"""
        _seed_rbac(temp_db)
        _add_user(temp_db, "root_actor", "ROOT")
        target_id = _add_user(temp_db, "root_target", "ADMIN")

        headers = _login(client, "root_actor")
        resp = _set_role(client, headers, target_id, "ROOT")
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "ROOT"
        print("[PASS] ROOT 可授予 ROOT")
