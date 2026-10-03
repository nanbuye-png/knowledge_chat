"""Phase A-1（M1-2）：修改密码 —— 后端行为 + 前端契约测试。

背景
----
审计 §5.14 把 ``/auth/change-password`` 列进"前端 4 处接口 404"：
``SecurityPage.tsx`` 一直在 POST ``/auth/change-password``（baseURL=/api），
而后端 ``api/auth.py`` 里**根本没有这个路由** —— 按钮点了只会 404，页面还
把 ``err.response.data.detail`` 当消息，连失败原因都显示不出来。

本文件同时钉住两侧：

1. 后端：路由存在、需认证、旧密码错→400、弱密码→400、与旧密码相同→400、
   成功后旧密码失效/新密码可登录、**其他 Session 立即失效而当前 Session 保留**、
   审计日志落库（SUCCESS / FAILURE 两条路径）；
2. 前端：``SecurityPage.tsx`` 的 apiClient 字面量必须命中真实路由，且前端
   密码策略与后端 ``core/password_policy.py`` 一致（不再是 ``length < 6``）。
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
)

# 本文件测契约/行为而不是限流：统一关掉限流（见 conftest.no_rate_limits）。
pytestmark = pytest.mark.usefixtures("no_rate_limits")

PAGE = "frontend/src/pages/account/SecurityPage.tsx"
OLD_PASSWORD = "Str0ng!Passw0rd123"
NEW_PASSWORD = "N3w!Passw0rd4567"


def _page_source() -> str:
    from tests.api_contract_utils import repo_root

    path = repo_root() / PAGE
    assert path.is_file(), f"找不到前端页面 {path}（契约测试必须同时看到两侧）"
    return path.read_text(encoding="utf-8")


def _register(client, username: str) -> None:
    resp = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": OLD_PASSWORD,
        },
    )
    assert resp.status_code in (200, 201), resp.text


def _login(client, username: str, password: str = OLD_PASSWORD) -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _change(client, headers, current: str, new: str):
    return client.post(
        "/api/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )


def _audit_entries(temp_db) -> list[tuple[str, str]]:
    """按 id 顺序返回 (action, status)，用于断言审计日志真的落库。"""
    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    async def _run():
        async with temp_db.session() as session:
            rows = (
                await session.execute(select(AuditLog).order_by(AuditLog.id))
            ).scalars().all()
            return [(row.action, row.status) for row in rows]

    return asyncio.run(_run())


class TestChangePasswordRoute:
    """路由与守卫：这个接口此前**根本不存在**（404）。"""

    def test_route_exists(self):
        assert ("POST", "/api/auth/change-password") in real_routes(), (
            "后端缺少 POST /api/auth/change-password（前端 SecurityPage 一直在调它）"
        )
        print("[PASS] POST /api/auth/change-password 已注册")

    def test_requires_auth(self, client):
        resp = client.post(
            "/api/auth/change-password",
            json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert resp.status_code == 401, resp.text
        print("[PASS] 未认证 → 401")

class TestChangePasswordRules:
    """业务规则：400 的三种来源 + 成功路径。"""

    def test_wrong_current_password_rejected(self, client):
        _register(client, "pw_wrong")
        headers = _headers(_login(client, "pw_wrong"))

        resp = _change(client, headers, "Wr0ng!Passw0rd999", NEW_PASSWORD)
        assert resp.status_code == 400, resp.text
        assert "当前密码" in resp.text, resp.text
        # 密码没被改动：旧密码仍能登录
        _login(client, "pw_wrong")
        print("[PASS] 当前密码错误 → 400 且密码未被修改")

    def test_weak_new_password_rejected(self, client):
        _register(client, "pw_weak")
        headers = _headers(_login(client, "pw_weak"))

        resp = _change(client, headers, OLD_PASSWORD, "Ab1!short")
        assert resp.status_code == 400, resp.text
        assert "12" in resp.text, resp.text
        print("[PASS] 弱密码（长度不足）→ 400 且提示最小长度")

    def test_new_password_without_special_char_rejected(self, client):
        _register(client, "pw_nospecial")
        headers = _headers(_login(client, "pw_nospecial"))

        resp = _change(client, headers, OLD_PASSWORD, "NoSpecialChar12345")
        assert resp.status_code == 400, resp.text
        assert "特殊字符" in resp.text, resp.text
        print("[PASS] 缺特殊字符 → 400")

    def test_same_password_rejected(self, client):
        _register(client, "pw_same")
        headers = _headers(_login(client, "pw_same"))

        resp = _change(client, headers, OLD_PASSWORD, OLD_PASSWORD)
        assert resp.status_code == 400, resp.text
        assert "相同" in resp.text, resp.text
        print("[PASS] 新旧密码相同 → 400")

    def test_success_switches_password(self, client):
        _register(client, "pw_ok")
        headers = _headers(_login(client, "pw_ok"))

        resp = _change(client, headers, OLD_PASSWORD, NEW_PASSWORD)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["message"], body
        assert body["revoked_sessions"] == 0, "只有一次登录，不该有『其他设备』可踢"

        # 旧密码失效（401），新密码可登录
        old = client.post(
            "/api/auth/login", json={"username": "pw_ok", "password": OLD_PASSWORD}
        )
        assert old.status_code == 401, old.text
        _login(client, "pw_ok", NEW_PASSWORD)
        print("[PASS] 改密码成功：旧密码 401、新密码可登录")


class TestChangePasswordSessions:
    """改密码即踢掉其他设备，但不踢自己。"""

    def test_other_sessions_revoked_current_kept(self, client):
        _register(client, "pw_multi")
        token_a = _login(client, "pw_multi")   # 当前设备
        token_b = _login(client, "pw_multi")   # 另一台设备

        assert client.get("/api/auth/me", headers=_headers(token_b)).status_code == 200

        resp = _change(client, _headers(token_a), OLD_PASSWORD, NEW_PASSWORD)
        assert resp.status_code == 200, resp.text
        assert resp.json()["revoked_sessions"] == 1, resp.text

        # 当前设备继续可用（否则用户改完密码自己立刻掉线）
        me = client.get("/api/auth/me", headers=_headers(token_a))
        assert me.status_code == 200, me.text

        # 另一台设备立即失效（Session revoked → get_current_user 拒绝）
        other = client.get("/api/auth/me", headers=_headers(token_b))
        assert other.status_code == 401, other.text

        sessions = client.get("/api/auth/sessions", headers=_headers(token_a)).json()
        assert len(sessions) == 2, sessions
        assert sum(1 for s in sessions if s["is_active"]) == 1, sessions
        print("[PASS] 其他 Session 立即 401，当前 Session 保留")


class TestChangePasswordAudit:
    """成功与失败都留痕（PASSWORD_CHANGE / SUCCESS|FAILURE）。"""

    def test_audit_log_written_for_failure_and_success(self, client, temp_db):
        _register(client, "pw_audit")
        headers = _headers(_login(client, "pw_audit"))

        assert _change(client, headers, "Wr0ng!Passw0rd999", NEW_PASSWORD).status_code == 400
        assert _change(client, headers, OLD_PASSWORD, NEW_PASSWORD).status_code == 200

        entries = [
            (action, status)
            for action, status in _audit_entries(temp_db)
            if action == "PASSWORD_CHANGE"
        ]
        assert ("PASSWORD_CHANGE", "FAILURE") in entries, entries
        assert ("PASSWORD_CHANGE", "SUCCESS") in entries, entries
        print(f"[PASS] 审计日志：{entries}")


class TestSecurityPageContract:
    """前端侧：页面调用命中真实路由，且策略与后端一致。"""

    def test_calls_resolve_to_real_routes(self):
        calls = iter_calls_in_file(PAGE)
        assert calls, f"扫描不到 {PAGE} 的 apiClient 调用（页面或正则已被改坏）"
        problems = contract_violations(calls)
        assert not problems, "前端调用了不存在的后端接口：\n" + "\n".join(problems)
        print(f"[PASS] {PAGE} 的 {len(calls)} 处调用全部命中真实路由")

    def test_uses_change_password_endpoint(self):
        pairs = {(call.method, call.expected_route) for call in iter_calls_in_file(PAGE)}
        assert ("POST", "/api/auth/change-password") in pairs, pairs
        print(f"[PASS] 页面调用：{sorted(pairs)}")

    def test_page_policy_matches_backend(self):
        source = _page_source()
        # 旧代码是 `if (newPw.length < 6) {...}`；现在必须走与后端同源的五条规则
        assert "newPw.length < 6" not in source, "前端仍是旧的 6 位策略，与后端 12 位不一致"
        assert "policyErrorOf(newPw)" in source, "页面未使用与后端一致的密码策略校验"
        assert "至少 12 位" in source, "页面必须提示后端真实的密码策略"
        assert "revoked_sessions" in source, "页面应消费改密码后踢掉其他设备的返回信息"
        print("[PASS] 页面密码策略与后端一致，并展示被踢设备数")
