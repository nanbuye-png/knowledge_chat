"""Sprint 30 综合集成测试：Organization CRUD + 成员管理 + 企业模型导入。

P0-5 修复说明
-------------
本文件原先写成模块级 ``async def run_all_tests()`` + ``if __name__ == "__main__"``，
没有任何 ``test_*`` 函数，因此 ``pytest --collect-only`` 收集到 **0 个用例** ——
这些"真实 SQLite 集成断言"在 CI 里从未运行过（审计 §8.2）。

现在改为标准 pytest 用例，并使用 ``conftest.py`` 的 ``temp_db`` fixture
（临时 SQLite 文件 + 全量建表，真实 SQL 往返，不是 ``AsyncMock``）。

覆盖:
1. Organization CRUD（创建 / 查询 / 按 slug 查询 / 列表 / 更新 / 删除）
2. Member management（添加 / 重复添加 / 改角色 / 列表 / 移除 / 重新激活）
3. 企业级模型可导入（Department, Group, KnowledgeACL, Quota, SystemConfig）
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)


# ---------------------------------------------------------------------------
# 场景实现（真实 SQL；断言内联，便于 pytest 直接定位失败点）
# ---------------------------------------------------------------------------


async def _organization_crud(temp_db) -> dict:
    """Organization 全生命周期。"""
    from app.schemas.organization import OrganizationCreate, OrganizationUpdate
    from app.services.organization import OrganizationService

    async with temp_db.session() as db:
        org = await OrganizationService.create(
            db, OrganizationCreate(name="测试组织", slug="test-org-crud"), owner_id=1
        )
        assert org.name == "测试组织"
        assert org.slug == "test-org-crud"
        assert org.is_active == True  # noqa: E712 - 与原用例保持一致

        org2 = await OrganizationService.get(db, org.id)
        assert org2 is not None and org2.id == org.id

        org3 = await OrganizationService.get_by_slug(db, "test-org-crud")
        assert org3 is not None and org3.slug == "test-org-crud"

        items, total = await OrganizationService.list(db, limit=10)
        assert total >= 1
        assert any(o.id == org.id for o in items), "列表应包含刚创建的组织"

        updated = await OrganizationService.update(
            db, org.id, OrganizationUpdate(name="更新组织名")
        )
        assert updated.name == "更新组织名"

        # 不存在的用户角色 → None
        role = await OrganizationService.get_user_role(db, 99999, 99999)
        assert role is None

        deleted = await OrganizationService.delete(db, org.id)
        assert deleted == True  # noqa: E712
        assert await OrganizationService.get(db, org.id) is None

        return {"org_id": org.id, "listed_total": total}


async def _member_management(temp_db) -> dict:
    """Organization 成员生命周期。"""
    from app.schemas.organization import OrganizationCreate
    from app.services.organization import (
        OrganizationMemberService,
        OrganizationService,
    )

    async with temp_db.session() as db:
        org = await OrganizationService.create(
            db, OrganizationCreate(name="成员测试", slug="member-test"), 1
        )

        member = await OrganizationMemberService.add_member(db, org.id, 2, "ADMIN")
        assert member.role == "ADMIN"
        assert member.is_active == True  # noqa: E712

        # 重复添加必须失败
        try:
            await OrganizationMemberService.add_member(db, org.id, 2, "MEMBER")
            raise AssertionError("重复添加成员应抛出 ValueError")
        except AssertionError:
            raise
        except ValueError as exc:
            assert "已是该组织成员" in str(exc)

        updated = await OrganizationMemberService.update_role(db, org.id, 2, "OWNER")
        assert updated.role == "OWNER"

        items, total = await OrganizationMemberService.list_members(db, org.id)
        assert total >= 2, f"owner + member 应至少 2 个，实际 {total}"
        assert len(items) == total

        removed = await OrganizationMemberService.remove_member(db, org.id, 2)
        assert removed == True  # noqa: E712
        after_remove = await OrganizationMemberService.get_member(db, org.id, 2)
        assert after_remove.is_active == False  # noqa: E712

        renewed = await OrganizationMemberService.add_member(db, org.id, 2, "MEMBER")
        assert renewed.is_active == True  # noqa: E712
        assert renewed.role == "MEMBER"

        return {"org_id": org.id, "members": total}


# ---------------------------------------------------------------------------
# pytest 用例
# ---------------------------------------------------------------------------


class TestOrganizationCRUD:
    def test_organization_crud_roundtrip(self, temp_db):
        """创建 → 查询 → slug 查询 → 列表 → 更新 → 删除（真实 SQLite）。"""
        summary = asyncio.run(_organization_crud(temp_db))
        assert summary["listed_total"] >= 1
        print(f"[PASS] Organization CRUD: org_id={summary['org_id']}")

    def test_duplicate_slug_isolated_per_test(self, temp_db):
        """每个用例拿到独立的临时库（互不污染）。"""
        from app.schemas.organization import OrganizationCreate
        from app.services.organization import OrganizationService

        async def scenario():
            async with temp_db.session() as db:
                items, total = await OrganizationService.list(db, limit=10)
                assert total == 0, "新临时库应为空"
                await OrganizationService.create(
                    db, OrganizationCreate(name="A", slug="dup-slug"), 1
                )
                items, total = await OrganizationService.list(db, limit=10)
                assert total == 1

        asyncio.run(scenario())
        print("[PASS] 临时库隔离正常")


class TestOrganizationMembers:
    def test_member_lifecycle(self, temp_db):
        """添加 → 重复 → 改角色 → 列表 → 移除 → 重新激活。"""
        summary = asyncio.run(_member_management(temp_db))
        assert summary["members"] >= 2
        print(f"[PASS] Member lifecycle: org_id={summary['org_id']}")


class TestEnterpriseModelImports:
    def test_models_importable(self):
        """企业级模型模块与类必须可导入（原先失败时静默 SKIP）。"""
        expected = [
            ("app.models.department", ["Department", "Group"]),
            ("app.models.knowledge_acl", ["KnowledgeACL"]),
            ("app.models.quota", ["Quota", "QuotaUsage"]),
            ("app.models.system_config", ["SystemConfig"]),
        ]
        imported = []
        for module_name, model_names in expected:
            module = __import__(module_name, fromlist=model_names)
            for name in model_names:
                assert hasattr(module, name), f"{name} 不在 {module_name} 中"
            imported.append(module_name)
        assert len(imported) == len(expected)
        print(f"[PASS] 企业模型导入: {', '.join(imported)}")


# ---------------------------------------------------------------------------
# 兼容旧的 ad-hoc 入口（CI 主入口现在是 pytest）
# ---------------------------------------------------------------------------


def run_all_tests() -> None:
    """手动运行全部场景（使用临时数据库，不触碰开发库）。"""
    from pathlib import Path

    from conftest import TempDatabase

    db = TempDatabase("sqlite+aiosqlite:///" + (Path("test_sprint30.db")).as_posix())
    asyncio.run(db.create_schema())
    try:
        TestOrganizationCRUD().test_organization_crud_roundtrip(db)
        TestOrganizationMembers().test_member_lifecycle(db)
        TestEnterpriseModelImports().test_models_importable()
        print("\n所有测试通过!")
    finally:
        asyncio.run(db.dispose())
        db_file = Path("test_sprint30.db")
        if db_file.exists():
            db_file.unlink()


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 30 综合集成测试 (Organization CRUD / Members / Models)")
    print("=" * 60)
    run_all_tests()
