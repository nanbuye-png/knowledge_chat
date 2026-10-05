"""LLM Model Provider 规范键契约测试（``agnes``；历史 ``agens`` 自动归一）。

背景（真实事故）
----------------
早期代码把 Provider 键写作 ``agens``（字母顺序写反），而厂商品牌名、模型 ID
（``agnes-2.5-flash``）与 Base URL（``apihub.agnes-ai.com``）都是 ``agnes``。
手工在「Model Registry」填 ``provider='agnes'`` 后，
``LLMProviderFactory.create_from_model()`` 抛 ``Unknown LLM provider: 'agnes'``，
Agent / 工作流对外统一显示「Agent 生成回答失败」，排查成本极高。

现在规范键统一为 ``agnes``，历史 ``agens`` 仅作别名。本文件锁定**写入口**两道防线
（运行期兜底见 ``test_llm_config.py::TestProviderAliasNormalization``）：

1. ``provider='agnes'`` → 返回体与落库值都是规范键 ``agnes``；
2. ``provider='agens'``（历史拼写 / 旧 .env / 老数据）→ 同样归一为 ``agnes``；
3. 不支持的 Provider（``openai``）→ 422，不允许脏数据落库；
4. 更新（PUT）同样归一，避免"创建时能用、改一下又坏"。

Run: cd backend && python -m pytest tests/test_llm_model_provider_alias.py -v
"""

import asyncio

import pytest

pytestmark = pytest.mark.usefixtures("no_rate_limits")

PASSWORD = "Str0ng!Passw0rd123"


def _register_and_login(client, username: str) -> dict:
    reg = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": PASSWORD,
        },
    )
    assert reg.status_code in (200, 201), reg.text
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _login_as_admin(client, temp_db, username: str) -> dict:
    """注册并登录，然后直接改库提权为 ADMIN（``/api/llm-models`` 仅管理员可用）。"""
    from sqlalchemy import select

    from app.models.user import User

    headers = _register_and_login(client, username)

    async def _run():
        async with temp_db.session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            user.role = "ADMIN"
            await session.commit()

    asyncio.run(_run())
    return headers


def _provider_of(temp_db, model_id: int) -> str:
    """直接读库确认落库值（不只看响应体）。"""
    from app.models.llm_model import LLMModel

    async def _run() -> str:
        async with temp_db.session() as session:
            model = await session.get(LLMModel, model_id)
            assert model is not None
            return model.provider

    return asyncio.run(_run())


class TestProviderAliasOnWrite:
    """API 写入侧必须把别名收敛成规范键，并挡住不支持的 Provider。"""

    def test_create_with_canonical_provider_is_kept(self, client, temp_db):
        headers = _login_as_admin(client, temp_db, "llm_alias_create")

        resp = client.post(
            "/api/llm-models",
            json={
                "name": "agnes",
                "provider": "agnes",
                "model_name": "agnes-2.5-flash",
            },
            headers=headers,
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["provider"] == "agnes", "规范键应原样保留"
        assert _provider_of(temp_db, body["id"]) == "agnes", "落库值必须是规范键"
        print("[PASS] provider='agnes' → 'agnes'（响应体 + 数据库）")

    def test_create_with_legacy_spelling_is_normalized(self, client, temp_db):
        headers = _login_as_admin(client, temp_db, "llm_alias_legacy")

        resp = client.post(
            "/api/llm-models",
            json={
                "name": "agnes-legacy",
                "provider": "agens",
                "model_name": "agnes-2.5-flash",
            },
            headers=headers,
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["provider"] == "agnes", "返回体必须归一（否则前端还会显示旧拼写）"
        assert _provider_of(temp_db, body["id"]) == "agnes", "落库值必须是规范键"
        print("[PASS] provider='agens'（历史拼写）→ 'agnes'（响应体 + 数据库）")

    def test_create_with_unsupported_provider_is_rejected(self, client, temp_db):
        headers = _login_as_admin(client, temp_db, "llm_alias_reject")

        resp = client.post(
            "/api/llm-models",
            json={"name": "x", "provider": "openai", "model_name": "gpt-4o"},
            headers=headers,
        )

        assert resp.status_code == 422, resp.text
        assert "不受支持" in resp.text
        print("[PASS] provider='openai' → 422（脏数据不进库）")

    def test_update_normalizes_legacy_spelling(self, client, temp_db):
        headers = _login_as_admin(client, temp_db, "llm_alias_update")
        created = client.post(
            "/api/llm-models",
            json={
                "name": "deepseek",
                "provider": "deepseek",
                "model_name": "deepseek-chat",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        model_id = created.json()["id"]

        resp = client.put(
            f"/api/llm-models/{model_id}",
            json={"provider": "agens", "model_name": "agnes-2.5-flash"},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["provider"] == "agnes"
        assert _provider_of(temp_db, model_id) == "agnes"
        print("[PASS] PUT provider='agens'（历史拼写）→ 'agnes'")

    def test_update_with_unsupported_provider_is_rejected(self, client, temp_db):
        headers = _login_as_admin(client, temp_db, "llm_alias_update_bad")
        created = client.post(
            "/api/llm-models",
            json={"name": "m", "provider": "agnes", "model_name": "agnes-2.5-flash"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        model_id = created.json()["id"]

        resp = client.put(
            f"/api/llm-models/{model_id}",
            json={"provider": "gemini"},
            headers=headers,
        )

        assert resp.status_code == 422, resp.text
        assert _provider_of(temp_db, model_id) == "agnes", "被拒请求不得改动原值"
        print("[PASS] PUT provider='gemini' → 422（原值不变）")
