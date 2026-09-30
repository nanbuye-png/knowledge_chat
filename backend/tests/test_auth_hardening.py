"""认证与时间语义硬化测试 —— 审计 §6.1-2 / §6.1-4。

审计原文（docs/KNOWLEDGE_CHAT_REALITY_AUDIT.md §6.1）：
    2) [P0 安全] get_current_user 不校验 is_active / deleted_at（auth/deps.py:58-59）
       → 软删除/禁用用户凭未过期 JWT（默认 24h）继续读写全部业务数据
    4) [P0 正确性] naive/aware datetime 混用：users.locked_until 读回为 naive，
       代码用 datetime.now(timezone.utc) 比较 → **账号锁定一旦触发，登录即 500**；
       同类问题导致 /api/auth/sessions、/api/admin/sessions、在线用户列表 500

这些用例全部走真实 SQLite + 真实路由：被删/被禁用户是"改库后拿旧 token 再请求"，
锁定用户是"改库后再登录"——即审计描述的原始复现路径。
"""

from datetime import timedelta

import pytest

from app.core.timeutil import utcnow

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


def _update_user(temp_db, username: str, **values) -> None:
    """直接改库，模拟"登录之后账号被禁用/软删除/锁定"。"""
    import asyncio

    from sqlalchemy import select

    from app.models.user import User

    async def _run():
        async with temp_db.session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            for key, value in values.items():
                setattr(user, key, value)
            await session.commit()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 1：账号锁定（naive/aware 混用 → 登录 500）
# ---------------------------------------------------------------------------


class TestAccountLockDatetime:
    def test_locked_account_login_returns_403_not_500(self, client, temp_db):
        """锁定后再次登录必须 403「已锁定」，而不是 500（审计 §6.1-4 原始复现）。"""
        _register_and_login(client, "locked_user")
        # SQLite 读回来的 locked_until 就是 naive —— 与旧代码的 aware now 比较必然炸
        _update_user(
            temp_db, "locked_user", locked_until=utcnow() + timedelta(minutes=10)
        )

        resp = client.post(
            "/api/auth/login", json={"username": "locked_user", "password": PASSWORD}
        )
        assert resp.status_code == 403, resp.text
        assert "锁定" in resp.text, resp.text
        print("[PASS] 锁定账号登录 → 403（此前 500）")

    def test_expired_lock_allows_login(self, client, temp_db):
        """锁定期已过 → 正常放行。"""
        _register_and_login(client, "unlocked_user")
        _update_user(
            temp_db, "unlocked_user", locked_until=utcnow() - timedelta(minutes=1)
        )

        resp = client.post(
            "/api/auth/login", json={"username": "unlocked_user", "password": PASSWORD}
        )
        assert resp.status_code == 200, resp.text
        print("[PASS] 锁定已过期 → 登录成功")

    def test_aware_locked_until_is_normalized(self, client, temp_db):
        """历史数据里可能存了 aware 值：归一后仍要正确判为"仍被锁定"。"""
        from datetime import datetime, timezone

        _register_and_login(client, "aware_locked_user")
        _update_user(
            temp_db,
            "aware_locked_user",
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=10),
        )

        resp = client.post(
            "/api/auth/login",
            json={"username": "aware_locked_user", "password": PASSWORD},
        )
        assert resp.status_code == 403, resp.text
        print("[PASS] aware locked_until 也能正确判为已锁定")


# ---------------------------------------------------------------------------
# 2：禁用 / 软删除用户的旧 token 立即失效
# ---------------------------------------------------------------------------


class TestTokenRevocationOnUserStateChange:
    def test_disabled_user_token_is_rejected(self, client, temp_db):
        headers = _register_and_login(client, "to_be_disabled")
        assert client.get("/api/knowledge-bases", headers=headers).status_code == 200

        _update_user(temp_db, "to_be_disabled", is_active=False)

        resp = client.get("/api/knowledge-bases", headers=headers)
        assert resp.status_code == 403, resp.text
        print("[PASS] 禁用后旧 token → 403")

    def test_soft_deleted_user_token_is_rejected(self, client, temp_db):
        headers = _register_and_login(client, "to_be_deleted")
        _update_user(temp_db, "to_be_deleted", deleted_at=utcnow())

        resp = client.get("/api/knowledge-bases", headers=headers)
        assert resp.status_code == 401, resp.text
        print("[PASS] 软删除后旧 token → 401")


# ---------------------------------------------------------------------------
# 3：会话 / 在线用户列表（同类 datetime 500）
# ---------------------------------------------------------------------------


def _login_as_admin(client, temp_db, username: str) -> dict:
    """注册并登录，然后直接改库提权为 ADMIN（并初始化 RBAC 默认角色）。"""
    import asyncio

    from sqlalchemy import select

    from app.models.user import User
    from app.services.auth.rbac_service import RBACService

    headers = _register_and_login(client, username)

    async def _run():
        async with temp_db.session() as session:
            await RBACService.init_default_roles(session)
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            user.role = "ADMIN"
            await session.commit()

    asyncio.run(_run())
    return headers


class TestSessionEndpointsDatetime:
    def test_admin_sessions_list_is_serializable(self, client, temp_db):
        """登录会写 user_sessions（expires_at 为 naive）→ 列表接口不能 500。"""
        headers = _login_as_admin(client, temp_db, "session_admin")

        resp = client.get("/api/admin/sessions", headers=headers)
        assert resp.status_code == 200, resp.text
        sessions = resp.json()
        assert sessions, "登录后应至少有一条 session"
        assert all(isinstance(s["is_active"], bool) for s in sessions), sessions
        print(f"[PASS] /api/admin/sessions → 200（{len(sessions)} 条，is_active 为布尔）")

    def test_online_users_endpoint_does_not_crash(self, client, temp_db):
        """/api/admin/users/online 要算 now - last_activity_at，不能再炸 naive/aware。"""
        headers = _login_as_admin(client, temp_db, "online_admin")

        resp = client.get("/api/admin/users/online", headers=headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert any(item["username"] == "online_admin" for item in items), items
        assert all(isinstance(item["online"], bool) for item in items), items
        print(f"[PASS] /api/admin/users/online → 200（{len(items)} 个用户）")


# ---------------------------------------------------------------------------
# 4：API Key 通道（审计 §6.1-3 / §6.1-6）
# ---------------------------------------------------------------------------


class TestApiKeyChannel:
    @staticmethod
    def _create_key(client, headers) -> str:
        resp = client.post("/api/api-keys", json={"name": "CI Key"}, headers=headers)
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["api_key"]

    def test_api_key_channel_works_and_expires(self, client, temp_db, monkeypatch):
        """审计 §6.1-3：API Key 通道此前实际不可达（依赖组合 + 缺表）。

        验证：建 Key → 用它调 /api/chat/chat 成功（LLM 用替身）→ 把 Key 改成
        已过期后同一个 Key 立即 401（而不是 500）。
        """
        import asyncio

        from sqlalchemy import select

        from app.api import chat as chat_api
        from app.models.api_key import ApiKey

        headers = _register_and_login(client, "apikey_user")
        raw_key = self._create_key(client, headers)

        async def _fake_chat(*args, **kwargs):
            return "替身回答"

        monkeypatch.setattr(chat_api.chat_service, "chat", _fake_chat)

        ok = client.post(
            "/api/chat/chat", json={"message": "你好"}, headers={"X-API-Key": raw_key}
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["answer"] == "替身回答"
        print("[PASS] X-API-Key 认证 + /api/chat/chat → 200")

        async def _expire():
            async with temp_db.session() as session:
                key = (await session.execute(select(ApiKey).limit(1))).scalar_one()
                key.expires_at = utcnow() - timedelta(minutes=1)
                await session.commit()

        asyncio.run(_expire())

        expired = client.post(
            "/api/chat/chat", json={"message": "你好"}, headers={"X-API-Key": raw_key}
        )
        assert expired.status_code == 401, expired.text
        print("[PASS] 过期 API Key → 401（此前 500）")

    def test_disabled_user_api_key_is_rejected(self, client, temp_db, monkeypatch):
        """禁用用户持有的 Key 必须立刻失效（与 JWT 同一条原则）。"""
        from app.api import chat as chat_api

        headers = _register_and_login(client, "apikey_disabled")
        raw_key = self._create_key(client, headers)

        async def _fake_chat(*args, **kwargs):
            return "替身回答"

        monkeypatch.setattr(chat_api.chat_service, "chat", _fake_chat)
        first = client.post(
            "/api/chat/chat", json={"message": "hi"}, headers={"X-API-Key": raw_key}
        )
        assert first.status_code == 200, first.text

        _update_user(temp_db, "apikey_disabled", is_active=False)

        resp = client.post(
            "/api/chat/chat", json={"message": "hi"}, headers={"X-API-Key": raw_key}
        )
        assert resp.status_code == 401, resp.text
        print("[PASS] 禁用用户的 API Key → 401")

