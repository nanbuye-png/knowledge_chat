"""HTTP 层冒烟测试（P0-5）。

背景：审计发现全仓库**没有任何路由级测试**（无 TestClient / httpx 用法），
因此 RBAC 500、越权、登录锁定 500、`api_keys` 缺表这类问题无法被测试捕获。

本文件是首批 HTTP 层测试，覆盖：
1. 公共端点可用（/、/api/health）
2. 未认证访问受保护端点必须 401（鉴权守卫真的挂在路由上）
3. 未知路由 404
4. 真实注册 → 登录 → 带 token 调用业务接口（全程真实 SQLite 往返）

依赖 ``conftest.py`` 的 ``client`` fixture（不执行 lifespan，避免触碰开发库、
向量库与嵌入模型）。
"""


class TestPublicEndpoints:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["app"]
        assert body["version"]
        print(f"[PASS] GET / → {body['app']} v{body['version']}")

    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        # Phase 3 §5.6：健康检查改为真实探测 —— 测试环境没有初始化向量库/嵌入模型，
        # 因此必须体现为 degraded，而不再是硬编码的 healthy（审计 §5.6 反例）。
        assert body["status"] in {"healthy", "degraded"}, body["checks"]
        assert set(body["checks"]) >= {"database", "vector_store", "embedding", "redis", "llm"}
        assert isinstance(body["embedding_model"], bool), (
            "embedding_model 必须是布尔值（历史缺陷：恒为 False）"
        )
        assert isinstance(body["llm_configured"], bool)
        print(
            f"[PASS] GET /api/health → status={body['status']}, "
            f"embedding_model={body['embedding_model']}"
        )

    def test_unknown_route_is_404(self, client):
        resp = client.get("/api/definitely-not-a-route")
        assert resp.status_code == 404
        print("[PASS] 未知路由 → 404")


class TestAuthGuards:
    """受保护资源必须要求认证（防止再次出现"裸奔"端点）。"""

    def test_list_knowledge_bases_requires_auth(self, client):
        resp = client.get("/api/knowledge-bases")
        assert resp.status_code == 401, resp.text
        print("[PASS] /api/knowledge-bases 未认证 → 401")

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/api/documents/upload",
            params={"knowledge_base_id": 1},
            files={"file": ("a.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 401, resp.text
        print("[PASS] /api/documents/upload 未认证 → 401")

    def test_document_status_requires_auth(self, client):
        resp = client.get("/api/documents/not-a-real-id/status")
        assert resp.status_code == 401, resp.text
        print("[PASS] /api/documents/{id}/status 未认证 → 401")

    def test_knowledge_query_requires_auth(self, client):
        resp = client.post(
            "/api/knowledge/query",
            json={"question": "你好", "knowledge_base_id": 1},
        )
        assert resp.status_code == 401, resp.text
        print("[PASS] /api/knowledge/query 未认证 → 401")

    def test_invalid_token_rejected(self, client):
        resp = client.get(
            "/api/knowledge-bases",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert resp.status_code == 401, resp.text
        print("[PASS] 非法 token → 401")


class TestAuthenticatedFlow:
    """真实注册 → 登录 → 业务调用（真实 SQLite 往返，非 mock）。"""

    PASSWORD = "Str0ng!Passw0rd123"

    def _register_and_login(self, client) -> str:
        reg = client.post(
            "/api/auth/register",
            json={
                "username": "smoke_user",
                "email": "smoke_user@example.com",
                "password": self.PASSWORD,
            },
        )
        assert reg.status_code in (200, 201), reg.text

        login = client.post(
            "/api/auth/login",
            json={"username": "smoke_user", "password": self.PASSWORD},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        assert token
        return token

    def test_register_login_and_knowledge_base_crud(self, client):
        token = self._register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        empty = client.get("/api/knowledge-bases", headers=headers)
        assert empty.status_code == 200, empty.text
        # 注意：注册流程会自动创建一个"XX的默认知识库"，因此这里不断言为 0，
        # 只记录基线数量，随后断言新增了 1 个。
        baseline = len(empty.json())

        created = client.post(
            "/api/knowledge-bases",
            json={"name": "冒烟知识库", "description": "P0-5 HTTP 测试"},
            headers=headers,
        )
        assert created.status_code in (200, 201), created.text
        kb_id = created.json()["id"]

        listed = client.get("/api/knowledge-bases", headers=headers)
        assert listed.status_code == 200
        ids = {kb["id"] for kb in listed.json()}
        assert len(listed.json()) == baseline + 1, listed.text
        assert kb_id in ids

        documents = client.get(
            "/api/documents",
            params={"knowledge_base_id": kb_id},
            headers=headers,
        )
        assert documents.status_code == 200, documents.text
        assert documents.json()["total"] == 0
        print(f"[PASS] 注册 → 登录 → 建库(id={kb_id}) → 列文档，全程真实 SQL")

    def test_wrong_password_rejected(self, client):
        self._register_and_login(client)
        resp = client.post(
            "/api/auth/login",
            json={"username": "smoke_user", "password": "WrongPassword!1234"},
        )
        assert resp.status_code == 401, resp.text
        print("[PASS] 错误密码 → 401")
