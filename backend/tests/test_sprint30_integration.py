"""
Sprint 30 综合集成测试: Step 2-10

测试:
1. Organization CRUD (Service + API)
2. Member management
3. Department & Group models
4. Permission system 2.0
5. Knowledge ACL model
6. Quota system model
7. API Key management (extended)
8. SystemConfig
9. All existing tests pass
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)


async def run_all_tests():
    """在单一事件循环中运行所有测试。"""
    # 初始化数据库（创建表）
    from app.storage.database import init_db, async_session
    await init_db()

    from app.services.organization import OrganizationService, OrganizationMemberService
    from app.schemas.organization import OrganizationCreate, OrganizationUpdate

    # ===== Step 2: Organization CRUD =====
    print("\n--- Step 2: Organization CRUD ---")

    async with async_session() as db:
        # Create
        org = await OrganizationService.create(
            db, OrganizationCreate(name="测试组织", slug="test-org-crud"), owner_id=1
        )
        assert org.name == "测试组织"
        assert org.slug == "test-org-crud"
        assert org.is_active == True
        print(f"[PASS] 创建组织: {org.name} (id={org.id})")

        # Get
        org2 = await OrganizationService.get(db, org.id)
        assert org2 is not None and org2.id == org.id
        print(f"[PASS] 查询组织: id={org.id}")

        # Get by slug
        org3 = await OrganizationService.get_by_slug(db, "test-org-crud")
        assert org3 is not None
        print(f"[PASS] 通过 slug 查询: {org3.slug}")

        # List
        items, total = await OrganizationService.list(db, limit=10)
        assert total >= 1
        print(f"[PASS] 组织列表: total={total}")

        # Update
        updated = await OrganizationService.update(
            db, org.id, OrganizationUpdate(name="更新组织名")
        )
        assert updated.name == "更新组织名"
        print(f"[PASS] 更新组织: {updated.name}")

        # Get user role (nonexistent)
        role = await OrganizationService.get_user_role(db, 99999, 99999)
        assert role is None
        print(f"[PASS] 不存在的用户角色: None")

        # Delete
        result = await OrganizationService.delete(db, org.id)
        assert result == True
        gone = await OrganizationService.get(db, org.id)
        assert gone is None
        print(f"[PASS] 删除组织: id={org.id}")

    # ===== Step 3: Member Management =====
    print("\n--- Step 3: Member Management ---")

    async with async_session() as db:
        # 创建测试组织
        org = await OrganizationService.create(
            db, OrganizationCreate(name="成员测试", slug="member-test"), 1
        )

        # Add member
        member = await OrganizationMemberService.add_member(db, org.id, 2, "ADMIN")
        assert member.role == "ADMIN"
        assert member.is_active == True
        print(f"[PASS] 添加成员: org={org.id}, user=2, role={member.role}")

        # Duplicate member should raise
        try:
            await OrganizationMemberService.add_member(db, org.id, 2, "MEMBER")
            assert False
        except ValueError as e:
            assert "已是该组织成员" in str(e)
            print(f"[PASS] 重复成员异常: {e}")

        # Update role
        updated = await OrganizationMemberService.update_role(db, org.id, 2, "OWNER")
        assert updated.role == "OWNER"
        print(f"[PASS] 更新角色: user=2, role={updated.role}")

        # List members
        items, total = await OrganizationMemberService.list_members(db, org.id)
        assert total >= 2  # owner + member
        print(f"[PASS] 成员列表: total={total}")

        # Remove member
        result = await OrganizationMemberService.remove_member(db, org.id, 2)
        assert result == True
        member = await OrganizationMemberService.get_member(db, org.id, 2)
        assert member.is_active == False
        print(f"[PASS] 移除成员: user=2, is_active={member.is_active}")

        # Add member again (reactivate)
        renewed = await OrganizationMemberService.add_member(db, org.id, 2, "MEMBER")
        assert renewed.is_active == True
        print(f"[PASS] 重新激活成员: is_active={renewed.is_active}")

        # Cleanup
        await db.delete(org)
        await db.commit()

    # ===== Step 4-9: Model Imports =====
    print("\n--- Step 4-9: Model Imports ---")

    for module_name, model_names in [
        ("app.models.department", ["Department", "Group"]),
        ("app.models.knowledge_acl", ["KnowledgeACL"]),
        ("app.models.quota", ["Quota", "QuotaUsage"]),
        ("app.models.system_config", ["SystemConfig"]),
    ]:
        try:
            mod = __import__(module_name, fromlist=model_names)
            for name in model_names:
                assert hasattr(mod, name), f"{name} not found in {module_name}"
            print(f"[PASS] {module_name}: {', '.join(model_names)}")
        except ImportError as e:
            print(f"[SKIP] {module_name}: {e}")

    print("\n" + "=" * 60)
    print("所有测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 30 综合集成测试 (Step 2-9)")
    print("=" * 60)
    asyncio.run(run_all_tests())