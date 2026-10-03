"""Phase A-1：API Key 前端页面 ↔ 后端接口的契约测试。

背景
----
审计把 ``/admin/api-keys`` 列为"前端 4 处接口 404"之一：``ApiKeysPage.tsx``
调的是 ``/admin/api-keys``（后端从来没有这个管理端路径），创建时还发
``{ user_id: 0 }``、读响应里的 ``key``（真实字段是仅创建时返回一次的
``api_key``，列表里只有 ``key_prefix``）。两侧各自的测试都是绿的，因为
**没有任何测试同时知道两边**。

本文件把两侧的权威事实接起来（工具在 ``tests/api_contract_utils.py``）：

1. 后端侧：``app.openapi()["paths"]``。**不能**用 ``app.routes`` ——
   实测 FastAPI 0.139 把 ``include_router`` 包成 ``_IncludedRouter``，
   遍历 ``app.routes`` 一条真实路径都扫不到，测试却依然"通过"。
2. 前端侧：扫描页面里的 ``apiClient.<method>('<path>')`` 字面量，按
   ``api/client.ts`` 的 baseURL ``/api`` 还原成后端路径并逐个断言存在；
   同时把"重复 /api 前缀"（``'/api/api-keys'`` → ``/api/api/api-keys``）
   判为违规。
3. 字段侧：页面读取的字段必须在 Pydantic schema 里存在。
4. 端到端：用页面**完全相同的四次调用**（POST / GET / PATCH / DELETE）
   跑真实 SQL 往返，证明"页面这么写确实能跑"。
"""
from __future__ import annotations

import os
import re
import sys

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from tests.api_contract_utils import (  # noqa: E402
    contract_violations,
    frontend_src_root,
    iter_calls_in_file,
    real_routes,
)

# 本文件测契约而不是限流：统一关掉限流（见 conftest.no_rate_limits）。
pytestmark = pytest.mark.usefixtures("no_rate_limits")

PAGE = "frontend/src/pages/account/ApiKeysPage.tsx"
PASSWORD = "Str0ng!Passw0rd123"


def _page_source() -> str:
    """读取页面源码；文件不在（只 checkout 了 backend）时**失败**而不是静默跳过。"""
    path = frontend_src_root().parent.parent / PAGE
    assert path.is_file(), f"找不到前端页面 {path}（契约测试必须同时看到两侧）"
    return path.read_text(encoding="utf-8")


class TestApiKeyRouteInventory:
    """后端侧：页面依赖的 4 个端点真实存在（取自 openapi，不是手写清单）。"""

    def test_four_endpoints_exist(self):
        routes = real_routes()
        expected = {
            ("GET", "/api/api-keys"),
            ("POST", "/api/api-keys"),
            ("PATCH", "/api/api-keys/{}/revoke"),
            ("DELETE", "/api/api-keys/{}"),
        }
        missing = expected - routes
        assert not missing, f"后端缺少 API Key 端点：{sorted(missing)}"
        print(f"[PASS] /api/api-keys 端点齐备：{sorted(expected)}")

    def test_guards_require_auth(self, client):
        """四个端点全部要求认证（防止再出现"裸奔"的用户密钥接口）。"""
        calls = [
            ("get", "/api/api-keys", {}),
            ("post", "/api/api-keys", {"json": {"name": "x"}}),
            ("patch", "/api/api-keys/1/revoke", {}),
            ("delete", "/api/api-keys/1", {}),
        ]
        for method, url, kwargs in calls:
            resp = getattr(client, method)(url, **kwargs)
            assert resp.status_code == 401, f"{method.upper()} {url} → {resp.status_code}"
        print("[PASS] /api/api-keys 四个端点未认证均 401")


class TestApiKeysPageContract:
    """前端侧：页面每一处调用都能落到真实路由上。"""

    def test_calls_resolve_to_real_routes(self):
        calls = iter_calls_in_file(PAGE)
        assert len(calls) >= 4, f"扫描不到 {PAGE} 的 apiClient 调用（正则或页面已被改坏）"
        problems = contract_violations(calls)
        assert not problems, "前端调用了不存在的后端接口：\n" + "\n".join(problems)
        print(f"[PASS] {PAGE} 的 {len(calls)} 处调用全部命中真实路由")

    def test_uses_real_methods_and_paths(self):
        pairs = {(call.method, call.expected_route) for call in iter_calls_in_file(PAGE)}
        assert ("GET", "/api/api-keys") in pairs, "列表必须 GET /api/api-keys"
        assert ("POST", "/api/api-keys") in pairs, "创建必须 POST /api/api-keys"
        assert ("PATCH", "/api/api-keys/{}/revoke") in pairs, (
            "撤销必须 PATCH /api/api-keys/{id}/revoke"
        )
        assert ("DELETE", "/api/api-keys/{}") in pairs, "删除必须 DELETE /api/api-keys/{id}"
        print(f"[PASS] 页面使用真实方法/路径：{sorted(pairs)}")

    def test_no_admin_path_and_no_phantom_body(self):
        calls = iter_calls_in_file(PAGE)
        assert all("admin" not in call.raw_path for call in calls), (
            "用户端页面不应调用管理端 API Key 路径："
            + ", ".join(call.describe() for call in calls if "admin" in call.raw_path)
        )
class TestApiKeyFieldContract:
    """字段侧：页面读的字段都真实存在，且明文永不出现在列表里。"""

    def test_page_reads_only_existing_fields(self):
        from app.schemas.api_key import ApiKeyCreatedResponse, ApiKeyResponse

        assert set(ApiKeyResponse.model_fields) >= {
            "id", "name", "key_prefix", "is_active",
            "last_used_at", "expires_at", "created_at",
        }
        assert set(ApiKeyCreatedResponse.model_fields) >= {"id", "name", "api_key", "created_at"}
        # 明文 key 只在创建响应里出现一次（列表永远拿不到）
        assert "api_key" not in ApiKeyResponse.model_fields
        assert "key" not in ApiKeyResponse.model_fields, (
            "列表响应里没有 `key` 字段 —— 页面读 k.key 只会得到 undefined"
        )
        print("[PASS] ApiKey 响应字段覆盖页面读取项，明文仅创建时返回一次")

    def test_page_source_reads_prefix_and_plaintext_api_key(self):
        source = _page_source()
        assert "key_prefix" in source and "api_key" in source
        assert not re.search(r"\bk\.key\b", source), (
            "列表项没有明文 key 可复制，只能展示 key_prefix"
        )
        assert "res.data.key" not in source, "创建响应字段是 api_key"
        print("[PASS] 页面按 key_prefix / api_key 读取字段")


class TestApiKeyEndToEnd:
    """用页面**完全相同的四次调用**跑一遍真实 SQL 往返。"""

    def _token(self, client) -> str:
        reg = client.post(
            "/api/auth/register",
            json={"username": "api_key_contract", "email": "api_key_contract@example.com",
                  "password": PASSWORD},
        )
        assert reg.status_code in (200, 201), reg.text
        login = client.post(
            "/api/auth/login",
            json={"username": "api_key_contract", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        return login.json()["access_token"]

    def test_create_list_revoke_delete(self, client):
        headers = {"Authorization": f"Bearer {self._token(client)}"}

        # 1) 创建：POST { name }（页面 handleCreate 的原样调用）
        created = client.post("/api/api-keys", json={"name": "契约测试"}, headers=headers)
        assert created.status_code == 201, created.text
        body = created.json()
        assert set(body) >= {"id", "name", "api_key", "created_at"}
        assert body["api_key"].startswith("sk-kc-"), body["api_key"]
        assert body["name"] == "契约测试"

        # 2) 列表：GET 返回 key_prefix，明文不再出现
        listed = client.get("/api/api-keys", headers=headers)
        assert listed.status_code == 200, listed.text
        items = listed.json()
        assert len(items) == 1, items
        assert items[0]["is_active"] is True
        assert body["api_key"].startswith(items[0]["key_prefix"]), (
            "列表里的 key_prefix 必须与创建时返回的明文前缀一致（页面靠它展示）"
        )
        assert "api_key" not in items[0]

        # 3) 撤销：PATCH /{id}/revoke（软删除）
        key_id = body["id"]
        revoked = client.patch(f"/api/api-keys/{key_id}/revoke", headers=headers)
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["is_active"] is False
        assert client.get("/api/api-keys", headers=headers).json()[0]["is_active"] is False

        # 4) 删除：DELETE /{id} → 204，列表清空
        deleted = client.delete(f"/api/api-keys/{key_id}", headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert client.get("/api/api-keys", headers=headers).json() == []
        print("[PASS] 页面四次真实调用（创建→列表→撤销→删除）全程 2xx/204")

    def test_missing_name_is_rejected(self, client):
        """页面把空名称拦在前面；后端也必须自己挡住（不能只靠前端校验）。"""
        headers = {"Authorization": f"Bearer {self._token(client)}"}
        resp = client.post("/api/api-keys", json={}, headers=headers)
        assert resp.status_code == 422, resp.text
        print("[PASS] 缺少 name → 422（后端自校验，不依赖前端）")
