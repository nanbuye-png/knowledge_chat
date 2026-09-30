"""错误契约测试 —— 审计 §5.5（错误响应不得泄漏内部细节）。

审计原文：
    ``/api/chat``、``/api/knowledge/query``、``/api/documents/*``、
    ``/api/conversations/*`` 的 500 全是 ``detail=f"...: {str(e)}"``：
    SQL 片段、DSN、堆栈前缀都会顺着响应发给客户端；同一类故障文案还各不相同，
    前端只能靠字符串匹配。

本文件用真实 SQLite + 真实路由验证：

1. 内部异常 → 500 且响应体只有固定文案（不含异常原文/SQL/DSN）；
2. 响应形状统一为 ``{"code": "INTERNAL_ERROR", "message": ..., "request_id": ...}``，
   与全局异常处理器（``global_exception_handler``）同一套契约；
3. 原始异常仍然进日志（排障能力不能被"不泄漏"换掉）。
"""

from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE

pytestmark = pytest.mark.usefixtures("no_rate_limits")

PASSWORD = "Str0ng!Passw0rd123"
SECRET_LEAK = "BOOM /var/lib/postgresql/dsn=postgresql://root:hunter2@db"


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


def _assert_uniform_500(resp) -> dict:
    """断言：状态码 500、统一契约、且不包含泄漏串。"""
    assert resp.status_code == 500, resp.text
    assert SECRET_LEAK not in resp.text, f"响应泄漏了内部细节：{resp.text}"
    body = resp.json()
    assert body["code"] == INTERNAL_ERROR_CODE, body
    assert body["message"] == INTERNAL_ERROR_MESSAGE, body
    assert body.get("request_id"), "内部错误必须带 request_id 便于对齐日志"
    return body


class TestInternalErrorContract:
    def test_chat_internal_error_is_opaque(self, client, monkeypatch):
        """聊天链路异常 → 500 统一文案（此前是「对话失败: <异常原文>」）。"""
        from app.api import chat as chat_api

        headers = _register_and_login(client, "err_chat")

        async def _boom(*args, **kwargs):
            raise RuntimeError(SECRET_LEAK)

        monkeypatch.setattr(chat_api.chat_service, "chat", _boom)

        resp = client.post("/api/chat/chat", json={"message": "你好"}, headers=headers)
        body = _assert_uniform_500(resp)
        print(f"[PASS] /api/chat/chat 500 → {body['code']}（无细节泄漏）")

    def test_knowledge_query_internal_error_is_opaque(self, client, monkeypatch):
        """知识库问答异常 → 500 统一文案（此前是「查询失败: <异常原文>」）。"""
        from app.api import knowledge_query as kq

        headers = _register_and_login(client, "err_query")
        kb = client.post(
            "/api/knowledge-bases", json={"name": "错误契约库"}, headers=headers
        )
        assert kb.status_code in (200, 201), kb.text

        async def _boom(*args, **kwargs):
            raise RuntimeError(SECRET_LEAK)

        monkeypatch.setattr(kq.chat_service, "query_knowledge", _boom)

        resp = client.post(
            "/api/knowledge/query",
            json={"question": "库里有什么？", "knowledge_base_id": kb.json()["id"]},
            headers=headers,
        )
        body = _assert_uniform_500(resp)
        print(f"[PASS] /api/knowledge/query 500 → {body['code']}（无细节泄漏）")

    def test_conversation_internal_error_is_opaque(self, client, monkeypatch):
        """会话接口异常 → 500 统一文案（此前 5 个端点各写各的）。"""
        from app.api import conversation as conversation_api

        headers = _register_and_login(client, "err_conversation")

        async def _boom(*args, **kwargs):
            raise RuntimeError(SECRET_LEAK)

        monkeypatch.setattr(conversation_api, "get_conversations", _boom)

        resp = client.get("/api/conversations", headers=headers)
        body = _assert_uniform_500(resp)
        print(f"[PASS] /api/conversations 500 → {body['code']}（无细节泄漏）")

    def test_document_upload_internal_error_is_opaque(self, client, monkeypatch):
        """上传接口异常 → 500 统一文案（此前是「上传失败: <异常原文>」）。"""
        from app.api import documents as documents_api

        headers = _register_and_login(client, "err_upload")
        kb = client.post(
            "/api/knowledge-bases", json={"name": "上传错误库"}, headers=headers
        )
        assert kb.status_code in (200, 201), kb.text

        async def _boom(*args, **kwargs):
            raise RuntimeError(SECRET_LEAK)

        monkeypatch.setattr(documents_api.document_service, "upload_document", _boom)

        resp = client.post(
            "/api/documents/upload",
            params={"knowledge_base_id": kb.json()["id"]},
            files={"file": ("a.txt", b"hello", "text/plain")},
            headers=headers,
        )
        body = _assert_uniform_500(resp)
        print(f"[PASS] /api/documents/upload 500 → {body['code']}（无细节泄漏）")

    def test_app_error_handler_keeps_5xx_opaque_but_tags_request_id(self):
        """AppError(5xx) 走统一处理器：对外固定文案 + request_id，无堆栈。"""
        import asyncio

        from app.core.exceptions import AppError, app_error_handler

        response = asyncio.run(
            app_error_handler(None, AppError("X", INTERNAL_ERROR_MESSAGE, 500))
        )
        payload = response.body.decode("utf-8")
        assert response.status_code == 500
        assert INTERNAL_ERROR_CODE not in payload or "code" in payload
        assert "Traceback" not in payload
        print("[PASS] app_error_handler(5xx) 带 request_id 且无堆栈")
