"""
Sprint 30 Step 1: Organization Core Model 测试

测试:
1. Organization 模型字段正确
2. OrganizationMember 模型字段和约束正确
3. User 与 Organization 的 relationship 连接正确
4. Schema 导入和验证
"""
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)


class TestOrganizationModel:
    """Organization 模型测试"""

    def _init_all_models(self):
        """通过 database 模块初始化所有模型，避免 string reference 问题"""
        from app.storage import database

    def test_model_imports(self):
        """模型导入正常"""
        self._init_all_models()
        from app.models.organization import Organization, OrganizationMember

        assert Organization.__tablename__ == "organizations"
        assert OrganizationMember.__tablename__ == "organization_members"
        print(f"[PASS] Organization table: {Organization.__tablename__}")
        print(f"[PASS] OrganizationMember table: {OrganizationMember.__tablename__}")

    def test_organization_fields(self):
        """Organization 字段"""
        self._init_all_models()
        from app.models.organization import Organization
        from sqlalchemy import inspect

        mapper = inspect(Organization)
        columns = {c.name: c for c in mapper.columns}

        expected = ["id", "name", "slug", "description", "is_active", "created_at", "updated_at"]
        for field in expected:
            assert field in columns, f"字段 {field} 不存在"
        print(f"[PASS] Organization fields: {list(columns.keys())}")

        assert columns["slug"].unique, "slug 未设置唯一索引"
        print("[PASS] Organization slug is unique")

    def test_organization_relationships(self):
        """Organization relationship"""
        self._init_all_models()
        from app.models.organization import Organization
        from sqlalchemy import inspect

        mapper = inspect(Organization)
        rels = {r.key: r for r in mapper.relationships}

        assert "members" in rels
        print(f"[PASS] Organization relationships: {list(rels.keys())}")

    def test_organization_member_fields(self):
        """OrganizationMember 字段和约束"""
        self._init_all_models()
        from app.models.organization import OrganizationMember
        from sqlalchemy import inspect, UniqueConstraint

        mapper = inspect(OrganizationMember)
        columns = {c.name: c for c in mapper.columns}

        expected = ["id", "organization_id", "user_id", "role", "joined_at", "is_active"]
        for field in expected:
            assert field in columns, f"字段 {field} 不存在"
        print(f"[PASS] OrganizationMember fields: {list(columns.keys())}")

        # 检查外键
        has_fk = any(c.foreign_keys for c in mapper.columns)
        assert has_fk, "缺少外键"
        print(f"[PASS] OrganizationMember has foreign keys")

        # 检查 UniqueConstraint
        constraints = [c for c in OrganizationMember.__table_args__ if isinstance(c, UniqueConstraint)]
        assert len(constraints) == 1, "缺少 UniqueConstraint"
        assert "uq_org_member" in [c.name for c in constraints]
        print(f"[PASS] OrganizationMember unique constraint: {constraints[0].name}")

    def test_user_relationship(self):
        """User 模型有 organizations 关系"""
        self._init_all_models()
        from app.models.user import User
        from sqlalchemy import inspect

        mapper = inspect(User)
        rels = {r.key: r for r in mapper.relationships}

        assert "organizations" in rels, "User 缺少 organizations relationship"
        print(f"[PASS] User relationships includes 'organizations'")

    def test_cascade_delete(self):
        """Organization 删除级联"""
        self._init_all_models()
        from app.models.organization import Organization
        from sqlalchemy import inspect

        org_mapper = inspect(Organization)
        org_rels = {r.key: r for r in org_mapper.relationships}

        assert org_rels["members"].cascade.delete_orphan
        print(f"[PASS] Organization -> members cascade delete-orphan")


class TestOrganizationSchema:
    """Organization Schema 测试"""

    def test_schema_imports(self):
        """Schema 导入正常"""
        from app.schemas.organization import (
            OrganizationCreate, OrganizationUpdate, OrganizationResponse,
            OrganizationMemberResponse, OrganizationMemberAdd,
            OrganizationMemberUpdateRole, OrganizationListResponse
        )
        print(f"[PASS] All schemas imported: {len(dir())} types")

    def test_organization_create(self):
        """OrganizationCreate 验证"""
        from app.schemas.organization import OrganizationCreate

        org = OrganizationCreate(name="Test Org", slug="test-org")
        assert org.name == "Test Org"
        assert org.slug == "test-org"
        assert org.description is None
        print(f"[PASS] OrganizationCreate: name={org.name}, slug={org.slug}")

        org2 = OrganizationCreate(name="Org 2", slug="org-2", description="desc")
        assert org2.description == "desc"
        print(f"[PASS] OrganizationCreate with description")

    def test_organization_response(self):
        """OrganizationResponse from_attributes"""
        from app.schemas.organization import OrganizationResponse
        assert OrganizationResponse.model_config.get("from_attributes") == True
        print(f"[PASS] OrganizationResponse from_attributes=True")

    def test_member_add(self):
        """OrganizationMemberAdd role 验证"""
        from app.schemas.organization import OrganizationMemberAdd

        add = OrganizationMemberAdd(user_id=1, role="OWNER")
        assert add.role == "OWNER"

        add2 = OrganizationMemberAdd(user_id=2, role="MEMBER")
        assert add2.role == "MEMBER"
        print(f"[PASS] OrganizationMemberAdd role validation works")


if __name__ == "__main__":
    print("=" * 50)
    print("Sprint 30 Step 1: Organization Core Model 测试")
    print("=" * 50)

    t1 = TestOrganizationModel()
    t1.test_model_imports()
    t1.test_organization_fields()
    t1.test_organization_relationships()
    t1.test_organization_member_fields()
    t1.test_user_relationship()
    t1.test_cascade_delete()

    t2 = TestOrganizationSchema()
    t2.test_schema_imports()
    t2.test_organization_create()
    t2.test_organization_response()
    t2.test_member_add()

    print("\n" + "=" * 50)
    print("所有测试通过!")
    print("=" * 50)