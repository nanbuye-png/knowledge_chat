"""知识库问答越权（IDOR）回归测试 —— 审计 §6.2。

审计原文（docs/KNOWLEDGE_CHAT_REALITY_AUDIT.md §6.2）：
    ``knowledge_query.py`` 只在 ``conversation_id is None`` 时校验知识库归属，
    因此「自己的会话 + 他人的 ``knowledge_base_id``」可以绕过检查检索他人知识库。

本文件用真实 SQLite（``conftest.py`` 的 ``client`` / ``temp_db`` fixture）跑完整
HTTP 往返，锁死三条规则：

1. 知识库归属校验**无条件**执行 —— 带自己的 ``conversation_id`` 也不能绕过；
2. 会话绑定的知识库必须与请求一致（纵深防御）；
3. 被拒绝的请求**不产生副作用** —— 不落库用户消息、不进入检索/LLM。

限流在本文件被显式关闭：这里测越权而不是限流，否则 5 次/分钟的登录限制
会让用例之间互相干扰（每个用例都要注册两个用户）。
"""

import json

import pytest

# 本文件测越权而不是限流：统一关掉限流（见 conftest.no_rate_limits）。
pytestmark = pytest.mark.usefixtures("no_rate_limits")

PASSWORD = "Str0ng!Passw0rd123"


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _register_and_login(client, username: str) -> dict:
    """注册并登录，返回可直接使用的认证头。"""
    reg = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": PASSWORD,
        },
    )
    assert reg.status_code in (200, 201), reg.text
    login = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_kb(client, headers, name: str) -> int:
    resp = client.post("/api/knowledge-bases", json={"name": name}, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _create_conversation(client, headers, kb_id: int) -> int:
    resp = client.post(
        "/api/conversations", json={"knowledge_base_id": kb_id}, headers=headers
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _list_messages(client, headers, conversation_id: int) -> list:
    resp = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _error_message(sse_body: str) -> str | None:
    """取出 SSE 里的 error 控制帧文案（与前端解析一致：``data:`` + token）。"""
    for line in sse_body.splitlines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            continue
        try:
            outer = json.loads(payload)
        except json.JSONDecodeError:
            continue
        token = outer.get("token")
        if not isinstance(token, str):
            continue
        try:
            inner = json.loads(token)
        except json.JSONDecodeError:
            continue
        if isinstance(inner, dict) and inner.get("type") == "error":
            return inner.get("message")
    return None


class _RecordingChatService:
    """chat_service 替身：只记录调用，避免真实检索/LLM（需要加载嵌入模型）。"""

    def __init__(self):
        self.calls: list[int] = []

    async def query_knowledge(self, question, knowledge_base_id, history, **kwargs):
        from app.schemas.chat import QueryResponse

        self.calls.append(knowledge_base_id)
        return QueryResponse(
            answer=f"命中知识库 {knowledge_base_id}", has_knowledge=True
        )

    async def stream_query_knowledge(self, *args, **kwargs):
        raise AssertionError("被拒绝的请求不应进入流式检索")
        yield ""  # pragma: no cover - 仅为让它成为 async generator


# ---------------------------------------------------------------------------
# 越权用例
# ---------------------------------------------------------------------------


class TestKnowledgeQueryAccessControl:
    def _setup(self, client) -> dict:
        alice = _register_and_login(client, "idor_alice")
        bob = _register_and_login(client, "idor_bob")
        alice_kb = _create_kb(client, alice, "Alice 的库")
        bob_kb = _create_kb(client, bob, "Bob 的库")
        alice_conv = _create_conversation(client, alice, alice_kb)
        alice_kb2 = _create_kb(client, alice, "Alice 的第二个库")
        return {
            "alice": alice,
            "bob": bob,
            "alice_kb": alice_kb,
            "alice_kb2": alice_kb2,
            "bob_kb": bob_kb,
            "alice_conv": alice_conv,
        }

    def test_other_users_knowledge_base_rejected_with_own_conversation(self, client):
        """审计 §6.2 的原始越权路径：自己的会话 + 他人的知识库 → 403。"""
        env = self._setup(client)

        resp = client.post(
            "/api/knowledge/query",
            json={
                "question": "Bob 的库里有什么？",
                "knowledge_base_id": env["bob_kb"],
                "conversation_id": env["alice_conv"],
            },
            headers=env["alice"],
        )
        assert resp.status_code == 403, resp.text
        assert "知识库" in resp.text, resp.text
        # 被拒绝的请求不得留下用户消息（校验必须在落库之前）
        assert _list_messages(client, env["alice"], env["alice_conv"]) == []
        print("[PASS] 自己的会话 + 他人的知识库 → 403，且未落库消息")

    def test_other_users_knowledge_base_rejected_without_conversation(self, client):
        """回退保护：无 conversation_id 时的既有校验不能丢。"""
        env = self._setup(client)

        resp = client.post(
            "/api/knowledge/query",
            json={"question": "Bob 的库里有什么？", "knowledge_base_id": env["bob_kb"]},
            headers=env["alice"],
        )
        assert resp.status_code == 403, resp.text
        print("[PASS] 无 conversation_id + 他人的知识库 → 403")

    def test_stream_rejects_other_users_knowledge_base(
        self, client, temp_db, monkeypatch
    ):
        """流式路径必须与同步路径一致：错误走 error 控制帧，且不进入检索。"""
        from app.api import knowledge_query as kq

        env = self._setup(client)
        recorder = _RecordingChatService()
        monkeypatch.setattr(kq, "async_session", temp_db.session)
        monkeypatch.setattr(kq, "chat_service", recorder)

        resp = client.post(
            "/api/knowledge/query/stream",
            json={
                "question": "Bob 的库里有什么？",
                "knowledge_base_id": env["bob_kb"],
                "conversation_id": env["alice_conv"],
            },
            headers=env["alice"],
        )
        assert resp.status_code == 200, resp.text
        message = _error_message(resp.text)
        assert message and "知识库" in message, resp.text
        assert recorder.calls == [], "越权请求不得进入检索/LLM"
        assert _list_messages(client, env["alice"], env["alice_conv"]) == []
        print(f"[PASS] 流式越权 → error 帧「{message}」，未进入检索")

    def test_conversation_knowledge_base_mismatch_rejected(self, client):
        """会话与请求的知识库必须一致（纵深防御）。"""
        env = self._setup(client)

        resp = client.post(
            "/api/knowledge/query",
            json={
                "question": "换个库问",
                "knowledge_base_id": env["alice_kb2"],
                "conversation_id": env["alice_conv"],  # 绑定的是 alice_kb
            },
            headers=env["alice"],
        )
        assert resp.status_code == 403, resp.text
        assert "不匹配" in resp.text, resp.text
        print("[PASS] 会话与知识库不一致 → 403")

    def test_legitimate_request_reaches_chat_service(self, client, monkeypatch):
        """合法请求必须仍然通过校验（防止修越权时误伤正常路径）。"""
        from app.api import knowledge_query as kq

        env = self._setup(client)
        recorder = _RecordingChatService()
        monkeypatch.setattr(kq, "chat_service", recorder)
        resp = client.post(
            "/api/knowledge/query",
            json={
                "question": "Alice 的库里有什么？",
                "knowledge_base_id": env["alice_kb"],
                "conversation_id": env["alice_conv"],
            },
            headers=env["alice"],
        )
        assert resp.status_code == 200, resp.text
        assert recorder.calls == [env["alice_kb"]]
        assert resp.json()["answer"] == f"命中知识库 {env['alice_kb']}"
        # 合法路径照常落库用户消息与回答
        messages = _list_messages(client, env["alice"], env["alice_conv"])
        assert [m["role"] for m in messages] == ["user", "assistant"], messages
        assert messages[1]["content"] == f"命中知识库 {env['alice_kb']}"
        print("[PASS] 合法请求 → 200，检索命中自身知识库并落库消息")

