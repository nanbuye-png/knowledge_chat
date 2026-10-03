"""Phase A-1（M1-3）：登录设备（Session）列表与"退出该设备"—— 契约 + 行为测试。

背景
----
审计 §5.15：``SessionsPage.tsx`` 读的四个字段（``device`` / ``ip`` /
``last_active`` / ``is_current``）在 ``SessionResponse`` 里**一个都不存在**
（后端返回 ``device_info`` / ``ip_address`` / ``last_used_at`` / ``is_active``），
所以卡片永远显示 "Unknown Device"、"IP: --"、时间 "--"，"当前设备"徽标永不出现；
页面还把请求写在 ``useState(() => {...})`` 里（render 期间发请求）；且看到陌生
设备也无法退出 —— 后端当时**没有用户端注销接口**（只有 ``user:manage`` 权限的
``DELETE /api/admin/sessions/{id}``）。

本文件钉住：
1. 路由存在（GET / DELETE）且都要求认证；
2. 列表字段契约 + ``is_current`` 每个 token 视角各自正确；
3. ``DELETE /api/auth/sessions/{id}``：退出他人设备 / 不许注销当前设备 /
   越权（他人 Session）→ 404 / 不存在 → 404 / 重复注销 → 400 / 审计留痕；
4. 前端 ``SessionsPage.tsx`` 的调用命中真实路由，且不再使用错位字段名。
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from tests.api_contract_utils import (  # noqa: E402
    contract_violations,
    iter_calls_in_file,
    real_routes,
    repo_root,
)

pytestmark = pytest.mark.usefixtures("no_rate_limits")

PAGE = "frontend/src/pages/account/SessionsPage.tsx"
PASSWORD = "Str0ng!Passw0rd123"

#: 列表响应必须覆盖的字段（前端 SessionsPage 逐字段消费）。
EXPECTED_FIELDS = {
    "id",
    "device_info",
    "ip_address",
    "created_at",
    "last_used_at",
    "expires_at",
    "revoked_at",
    "is_active",
    "is_current",
}


def _page_source() -> str:
    path = repo_root() / PAGE
    assert path.is_file(), f"找不到前端页面 {path}（契约测试必须同时看到两侧）"
    return path.read_text(encoding="utf-8")


def _register(client, username: str) -> None:
    resp = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": PASSWORD,
        },
    )
    assert resp.status_code in (200, 201), resp.text


def _login(client, username: str) -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _sessions(client, token: str) -> list[dict]:
    resp = client.get("/api/auth/sessions", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _other_session_id(client, token: str) -> int:
    """当前 token 之外的那条 Session 的 id。"""
    others = [s for s in _sessions(client, token) if not s["is_current"]]
    assert others, f"应存在至少一条非当前 Session：{_sessions(client, token)}"
    return others[0]["id"]


def _audit_entries(temp_db) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    async def _run():
        async with temp_db.session() as session:
            rows = (
                await session.execute(select(AuditLog).order_by(AuditLog.id))
            ).scalars().all()
            return [(row.action, row.status) for row in rows]

    return asyncio.run(_run())


class TestSessionsRoutes:
    """路由与守卫：用户端注销接口此前根本不存在。"""

    def test_routes_exist(self):
        routes = real_routes()
        assert ("GET", "/api/auth/sessions") in routes, "缺少 GET /api/auth/sessions"
        assert ("DELETE", "/api/auth/sessions/{}") in routes, (
            "缺少 DELETE /api/auth/sessions/{session_id}（页面无法退出其他设备）"
        )
        print("[PASS] GET / DELETE /api/auth/sessions 均已注册")

    def test_requires_auth(self, client):
        assert client.get("/api/auth/sessions").status_code == 401
        assert client.delete("/api/auth/sessions/1").status_code == 401
        print("[PASS] 列表与注销都需要认证 → 401")


class TestSessionsListContract:
    """列表字段契约 + is_current。"""

    def test_response_fields_match_page(self, client):
        _register(client, "sess_fields")
        token = _login(client, "sess_fields")

        items = _sessions(client, token)
        assert len(items) == 1, items
        missing = EXPECTED_FIELDS - set(items[0])
        assert not missing, f"列表缺少前端消费的字段：{missing}"
        print(f"[PASS] 列表字段齐全：{sorted(items[0])}")

    def test_is_current_is_per_token(self, client):
        _register(client, "sess_current")
        token_a = _login(client, "sess_current")
        token_b = _login(client, "sess_current")

        for token in (token_a, token_b):
            flags = [s["is_current"] for s in _sessions(client, token)]
            assert flags.count(True) == 1, f"每个 token 视角应恰好一条 current：{flags}"
        print("[PASS] is_current 按请求 token 判定（两个设备各自视角正确）")


class TestRevokeOwnSession:
    """退出该设备：只动自己的、不动当前的。"""

    def test_revoke_other_device(self, client):
        _register(client, "sess_revoke")
        token_a = _login(client, "sess_revoke")
        token_b = _login(client, "sess_revoke")

        other_id = _other_session_id(client, token_a)
        resp = client.delete(f"/api/auth/sessions/{other_id}", headers=_headers(token_a))
        assert resp.status_code == 200, resp.text
        assert resp.json()["session_id"] == other_id, resp.text

        # 另一台设备立即失效，当前设备不受影响
        assert client.get("/api/auth/me", headers=_headers(token_b)).status_code == 401
        assert client.get("/api/auth/me", headers=_headers(token_a)).status_code == 200

        items = _sessions(client, token_a)
        revoked = [s for s in items if s["id"] == other_id][0]
        assert revoked["is_active"] is False and revoked["revoked_at"], revoked
        print("[PASS] 退出其他设备：目标立即 401、当前设备保留、列表标记已退出")

    def test_cannot_revoke_current_device(self, client):
        _register(client, "sess_self")
        token = _login(client, "sess_self")
        current_id = [s for s in _sessions(client, token) if s["is_current"]][0]["id"]

        resp = client.delete(f"/api/auth/sessions/{current_id}", headers=_headers(token))
        assert resp.status_code == 400, resp.text
        assert "退出登录" in resp.text, resp.text
        # 自己没被踢掉
        assert client.get("/api/auth/me", headers=_headers(token)).status_code == 200
        print("[PASS] 注销当前设备被拒绝（语义是退出登录），token 仍可用")

    def test_cannot_revoke_other_users_session(self, client):
        _register(client, "sess_victim")
        victim_token = _login(client, "sess_victim")
        victim_session = _sessions(client, victim_token)[0]["id"]

        _register(client, "sess_attacker")
        attacker_token = _login(client, "sess_attacker")

        resp = client.delete(
            f"/api/auth/sessions/{victim_session}", headers=_headers(attacker_token)
        )
        assert resp.status_code == 404, resp.text
        # 越权失败且受害者会话未被破坏
        assert client.get("/api/auth/me", headers=_headers(victim_token)).status_code == 200
        print("[PASS] 越权注销他人 Session → 404 且未生效")

    def test_revoke_unknown_and_twice(self, client):
        _register(client, "sess_missing")
        token = _login(client, "sess_missing")
        _login(client, "sess_missing")  # 制造第二条，供重复注销

        assert client.delete(
            "/api/auth/sessions/999999", headers=_headers(token)
        ).status_code == 404

        other_id = _other_session_id(client, token)
        assert client.delete(
            f"/api/auth/sessions/{other_id}", headers=_headers(token)
        ).status_code == 200
        second = client.delete(f"/api/auth/sessions/{other_id}", headers=_headers(token))
        assert second.status_code == 400, second.text
        assert "已被注销" in second.text, second.text
        print("[PASS] 不存在 → 404；重复注销 → 400")

    def test_revoke_is_audited(self, client, temp_db):
        _register(client, "sess_audit")
        token = _login(client, "sess_audit")
        _login(client, "sess_audit")

        other_id = _other_session_id(client, token)
        assert client.delete(
            f"/api/auth/sessions/{other_id}", headers=_headers(token)
        ).status_code == 200

        actions = [a for a, _ in _audit_entries(temp_db)]
        assert "REVOKE_SESSION" in actions, actions
        print(f"[PASS] 审计日志含 REVOKE_SESSION：{actions}")


class TestSessionsPageContract:
    """前端侧：调用命中真实路由，且不再读错位字段。"""

    def test_calls_resolve_to_real_routes(self):
        calls = iter_calls_in_file(PAGE)
        assert calls, f"扫描不到 {PAGE} 的 apiClient 调用（页面或正则已被改坏）"
        problems = contract_violations(calls)
        assert not problems, "前端调用了不存在的后端接口：\n" + "\n".join(problems)
        print(f"[PASS] {PAGE} 的 {len(calls)} 处调用全部命中真实路由")

    def test_uses_real_methods_and_paths(self):
        pairs = {(call.method, call.expected_route) for call in iter_calls_in_file(PAGE)}
        assert ("GET", "/api/auth/sessions") in pairs, pairs
        assert ("DELETE", "/api/auth/sessions/{}") in pairs, (
            f"页面必须调用 DELETE /api/auth/sessions/{{id}} 才能退出设备：{pairs}"
        )
        print(f"[PASS] 页面调用：{sorted(pairs)}")

    def test_page_uses_real_field_names(self):
        source = _page_source()
        for field in ("device_info", "ip_address", "last_used_at", "is_current"):
            assert field in source, f"页面未使用后端真实字段 {field}"
        assert "useEffect" in source, "加载必须放在 useEffect 里（不能 render 期间发请求）"
        # 旧实现的代码特征（注释里提到旧实现不算残留，这里的 marker 只出现在代码中）
        for legacy in ("s.device ", "s.ip ", "s.last_active", ".then((res) => setSessions"):
            assert legacy not in source, f"页面仍残留旧实现：{legacy!r}"
        print("[PASS] 页面字段与后端 SessionResponse 对齐，且不再 render 期发请求")

