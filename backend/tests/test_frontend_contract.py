"""Phase 3 §5.4 前端契约回归测试。

背景
----
审计 §5.4 的关键教训：前端是"后端契约的最后一个知情人"。上传幂等的
``skipped`` / ``duplicated_of``、流式控制帧（``sources`` / ``no_result`` /
``error``）、统一错误信封 ``{"code","message"}``、文档状态 ``pending`` ——
这些字段此前都只靠人肉对齐，任何一方改动都不会让测试变红，
于是"后端加 /stream 绕过限流""拒答被当成模型回答""上传重复文件前端一直转圈"
才能一路带病上线。

本文件把**前端真正解析的字段与分派逻辑**写成断言（相当于在 Python 里重放
``frontend/src/api/sse.ts`` + ``api/knowledge.ts`` + ``api/chat.ts`` +
``api/documents.ts`` + ``types/index.ts``）：

1. 上传响应（§5.3）：字段集合、重复上传被跳过、且**未派发处理任务**。
2. RAG 流式帧（§5.4/§5.6）：正文 token、``sources``（含 citations）、
   ``no_result``（abstained/reason/message）、``error``、``[DONE]``。
3. 通用对话流式帧：正文 token、``error`` 控制帧（不能把错误当回答渲染）。
4. 非流式 /api/knowledge/query 与 schema 字段（前端 TS 接口的镜像）。
5. 统一错误信封（前端 ``extractErrorMessage`` 首选顶层 ``message``）。

注意：帧由**真实**的 ``ChatService`` 产出（只替换检索/LLM 依赖），
不是手工拼两个字符串 —— 否则"真实实现改了帧，测试仍然绿"。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.config import settings  # noqa: E402
from app.schemas.chat import QueryRequest  # noqa: E402
from app.services.retrieval.abstention import AbstentionDecider  # noqa: E402
from app.services.retrieval.models import RetrievalResult  # noqa: E402


# ---------------------------------------------------------------------------
# 前端解析逻辑的等价重放（frontend/src/api/sse.ts）
# ---------------------------------------------------------------------------


def frontend_sse_payloads(chunks: list[str]) -> tuple[list[str], bool]:
    """等价于 ``readSse()``：逐行取 ``data: `` 载荷，遇 ``[DONE]`` 停止。"""
    payloads: list[str] = []
    for chunk in chunks:
        for line in chunk.split("\n"):
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                return payloads, True
            payloads.append(payload)
    return payloads, False


def frontend_parse_control_frame(token: str):
    """等价于 ``parseControlFrame()``：token 内嵌 JSON 且带 ``type`` 才算控制帧。"""
    trimmed = token.strip()
    if not trimmed.startswith("{"):
        return None
    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("type"), str):
        return parsed
    return None


def frontend_parse_knowledge_stream(chunks: list[str]) -> dict:
    """等价于 ``createStreamKnowledgeQuery()`` 的控制帧分发。"""
    state: dict = {
        "tokens": "", "sources": [], "citations": [],
        "abstention": None, "error": None, "stopped": False, "saw_done": False,
    }
    payloads, saw_done = frontend_sse_payloads(chunks)
    state["saw_done"] = saw_done

    for payload in payloads:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        token = parsed.get("token")
        if not isinstance(token, str):
            continue

        frame = frontend_parse_control_frame(token)
        if frame is None:
            state["tokens"] += token
            continue

        if frame["type"] == "sources":
            state["sources"] = frame.get("sources") or []
            state["citations"] = frame.get("citations") or []
        elif frame["type"] == "no_result":
            state["abstention"] = {
                "abstained": frame.get("abstained", True),
                "reason": frame.get("reason"),
                "message": frame.get("message", ""),
            }
            state["stopped"] = True
            return state
        elif frame["type"] == "error":
            state["error"] = frame.get("message")
            state["stopped"] = True
            return state
    return state


def frontend_parse_chat_stream(chunks: list[str]) -> dict:
    """等价于 ``createStreamChat()`` 的控制帧分发。"""
    state: dict = {"tokens": "", "error": None, "saw_done": False}
    payloads, saw_done = frontend_sse_payloads(chunks)
    state["saw_done"] = saw_done

    for payload in payloads:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        token = parsed.get("token")
        if not isinstance(token, str):
            continue

        frame = frontend_parse_control_frame(token)
        if frame is None:
            state["tokens"] += token
            continue
        if frame["type"] == "error":
            state["error"] = frame.get("message")
            return state
    return state


# ---------------------------------------------------------------------------
# 服务替身（只替换检索与 LLM，帧仍由真实 ChatService 产出）
# ---------------------------------------------------------------------------

_CHUNK = {
    "id": "chunk-0",
    "document_id": "doc-1",
    "filename": "manual.pdf",
    "chunk_index": 0,
    "text": "门诊时间为周一至周五 8:00-17:00。",
    "score": 0.92,
    "page": 3,
    "section": "营业时间",
}


def _retrieval_result(chunks: list[dict] | None = None) -> RetrievalResult:
    from app.services.citation.builder import CitationBuilder

    chunks = chunks or []
    return RetrievalResult(
        results=chunks,
        context="[来源1] manual.pdf：门诊时间为周一至周五 8:00-17:00。",
        sources=[
            {
                "document_id": c["document_id"],
                "filename": c["filename"],
                "chunk_index": c["chunk_index"],
                "text": c["text"],
                "page": c.get("page"),
                "section": c.get("section"),
            }
            for c in chunks
        ],
        citations=CitationBuilder().build(chunks),
        has_results=bool(chunks),
    )


class _StubRetrieval:
    def __init__(self, result: RetrievalResult, error: Exception | None = None):
        self.result = result
        self.error = error

    async def retrieve(self, question, knowledge_base_id, history=None, **kwargs):
        if self.error is not None:
            raise self.error
        return self.result


class _StubPromptProvider:
    """最小提示词提供者（真实 provider 会查库，与本次契约无关）。"""

    async def get_system_prompt(self) -> str:
        return "你是知识库助手。"

    async def get_rag_prompt(self, context: str, question: str) -> str:
        return f"上下文：\n{context}\n\n问题：{question}"


async def _fake_stream_llm(**kwargs):
    yield "根据"
    yield "文档，"
    yield "门诊时间为 8:00-17:00。"


async def _failing_stream_llm(**kwargs):
    raise RuntimeError("Error code: 429 - rate limit")
    yield ""  # pragma: no cover - 仅为让它成为 async generator


class _FakeSessionContext:
    """``async with async_session() as db`` 的替身。"""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _patch_chat_service(monkeypatch, retrieval, llm=None, decider=None):
    """替换检索/LLM/提示词依赖，保留真实的 ChatService 帧生成逻辑。"""
    from app.services import chat_service as chat_service_module

    service = chat_service_module.chat_service
    if not isinstance(retrieval, _StubRetrieval):
        retrieval = _StubRetrieval(retrieval)
    monkeypatch.setattr(service, "_retrieval", retrieval)
    monkeypatch.setattr(service, "_abstention", decider or AbstentionDecider())
    # 实例属性赋值不会绑定 self，故替身签名用 **kwargs
    monkeypatch.setattr(service, "_stream_llm", llm or _fake_stream_llm)
    monkeypatch.setattr(
        service, "get_prompt_provider", AsyncMock(return_value=_StubPromptProvider())
    )
    return service


def _run_knowledge_route(
    monkeypatch, question: str = "门诊时间？", conversation_id: int | None = None
) -> tuple[list[str], dict]:
    """走真实的 /api/knowledge/query/stream 路由。

    Returns:
        ``(chunks, saved)``；``saved`` 收集落库的 user/assistant 消息。
    """
    from app.api import knowledge_query as kq

    monkeypatch.setattr(kq, "async_session", lambda: _FakeSessionContext(AsyncMock()))
    monkeypatch.setattr(kq, "update_user_activity", AsyncMock())
    monkeypatch.setattr(kq, "verify_knowledge_base_access", AsyncMock())
    # 会话绑定的知识库与请求一致（审计 §6.2 新增的一致性校验，请求 kb=1）
    ownership = AsyncMock()
    ownership.return_value.knowledge_base_id = 1
    monkeypatch.setattr(kq, "_verify_conversation_ownership", ownership)
    monkeypatch.setattr(kq, "auto_update_conversation_title", AsyncMock())

    saved: dict = {"user": [], "assistant": []}

    async def _create_user_message(_db, cid, content):
        saved["user"].append((cid, content))

    async def _create_assistant_message(_db, cid, content):
        saved["assistant"].append((cid, content))

    monkeypatch.setattr(kq, "create_user_message", _create_user_message)
    monkeypatch.setattr(kq, "create_assistant_message", _create_assistant_message)

    request = QueryRequest(
        question=question, knowledge_base_id=1, conversation_id=conversation_id
    )

    async def _collect():
        response = await kq.stream_query_knowledge(request, current_user=MagicMock(id=1))
        return [chunk async for chunk in response.body_iterator]

    return asyncio.run(_collect()), saved


def _run_chat_route(
    monkeypatch,
    message: str = "你好",
    conversation_id: int | None = None,
    verify_error: Exception | None = None,
) -> list[str]:
    """走真实的 /api/chat/stream 路由，返回 SSE 帧列表。"""
    from app.api import chat as chat_api
    from app.schemas.chat import ChatRequest

    async def _verify(_db, _cid, _uid):
        if verify_error is not None:
            raise verify_error

    async def _fake_stream_chat(*args, **kwargs):
        yield "你好"
        yield "，世界"

    monkeypatch.setattr(chat_api, "async_session", lambda: _FakeSessionContext(AsyncMock()))
    monkeypatch.setattr(chat_api, "update_user_activity", AsyncMock())
    monkeypatch.setattr(chat_api, "_verify_conversation_ownership", _verify)
    monkeypatch.setattr(chat_api, "auto_update_conversation_title", AsyncMock())
    monkeypatch.setattr(chat_api, "create_user_message", AsyncMock())
    monkeypatch.setattr(chat_api, "create_assistant_message", AsyncMock())
    monkeypatch.setattr(chat_api.chat_service, "stream_chat", _fake_stream_chat)

    request = ChatRequest(message=message, conversation_id=conversation_id)

    async def _collect():
        response = await chat_api.stream_chat(request, current_user=MagicMock(id=1))
        return [chunk async for chunk in response.body_iterator]

    return asyncio.run(_collect())


# ---------------------------------------------------------------------------
# 1: RAG 流式帧契约（/api/knowledge/query/stream）
# ---------------------------------------------------------------------------


class TestKnowledgeStreamContract:
    """帧必须能被 frontend/src/api/knowledge.ts 的解析逻辑消费。"""

    def test_sources_frame_carries_frontend_fields(self, monkeypatch):
        _patch_chat_service(monkeypatch, _retrieval_result([_CHUNK]))

        chunks, _ = _run_knowledge_route(monkeypatch)
        state = frontend_parse_knowledge_stream(chunks)

        assert all(c.startswith("data: ") for c in chunks), "帧必须以 'data: ' 开头"
        assert all(c.endswith("\n\n") for c in chunks), "帧必须以空行结束（SSE）"
        assert chunks[-1] == "data: [DONE]\n\n", "结束帧契约"
        assert state["saw_done"] is True

        # sources：前端渲染引用列表要用的字段
        assert state["sources"], "正常路径必须发 sources 控制帧"
        source = state["sources"][0]
        assert set(source) >= {"document_id", "filename", "chunk_index", "text"}
        assert source["filename"] == "manual.pdf"
        assert source["text"]

        # citations：§5.5 结构化引用（此前前端直接丢弃）
        assert state["citations"], "sources 帧必须同时带 citations"
        citation = state["citations"][0]
        assert set(citation) >= {"document_id", "filename", "chunk_id", "score", "display"}

        # 正文 token 拼接后就是完整回答
        assert state["tokens"] == "根据文档，门诊时间为 8:00-17:00。"
        assert state["error"] is None
        print(f"[PASS] sources 帧可被前端解析: {source['filename']}, citations={len(state['citations'])}")

    def test_abstention_frame_carries_reason(self, monkeypatch):
        _patch_chat_service(monkeypatch, _retrieval_result([]))

        chunks, _ = _run_knowledge_route(monkeypatch)
        state = frontend_parse_knowledge_stream(chunks)

        # 控制帧的 token 带尾部换行，前端依赖 trim 后解析（此处锁死该约定）
        token = json.loads(chunks[0][6:].strip())["token"]
        assert token.endswith("\n")
        assert frontend_parse_control_frame(token) is not None

        assert state["abstention"] is not None, "拒答必须走 no_result 控制帧"
        assert state["abstention"]["abstained"] is True
        assert state["abstention"]["reason"] == "no_context"
        assert state["abstention"]["message"], "前端要展示的拒答文案不能为空"
        assert state["tokens"] == "", "拒答帧不得被当成正文渲染"
        print(f"[PASS] 拒答帧可被前端解析: reason={state['abstention']['reason']}")

    def test_abstention_message_is_persisted(self, monkeypatch):
        """拒答也必须落库：否则用户重开会话只看到自己的提问，看不到系统答了什么。"""
        _patch_chat_service(monkeypatch, _retrieval_result([]))

        chunks, saved = _run_knowledge_route(
            monkeypatch, question="有没有年假？", conversation_id=7
        )
        state = frontend_parse_knowledge_stream(chunks)

        assert saved["user"] == [(7, "有没有年假？")]
        assert saved["assistant"] == [(7, state["abstention"]["message"])]
        print(f"[PASS] 拒答文案已落库: {saved['assistant'][0][1]}")

    def test_failure_frame_is_control_frame_not_answer(self, monkeypatch):
        _patch_chat_service(
            monkeypatch, _retrieval_result([_CHUNK]), llm=_failing_stream_llm
        )

        chunks, saved = _run_knowledge_route(monkeypatch)
        state = frontend_parse_knowledge_stream(chunks)

        assert state["error"], "生成失败必须走 error 控制帧（走 onError 而不是正文）"
        assert "429" not in state["tokens"], "内部报文不能出现在正文里"
        assert state["stopped"] is True
        assert saved["assistant"] == [], "失败的问答不得写入会话历史"
        print(f"[PASS] 失败帧走 onError: {state['error']}")

    def test_retrieval_failure_yields_error_frame(self, monkeypatch):
        _patch_chat_service(
            monkeypatch,
            _StubRetrieval(_retrieval_result([]), error=RuntimeError("vector store down")),
        )

        chunks, _ = _run_knowledge_route(monkeypatch)
        state = frontend_parse_knowledge_stream(chunks)

        assert state["error"]
        assert state["abstention"] is None, "系统故障不是拒答"
        print(f"[PASS] 检索异常走 error 控制帧: {state['error']}")


# ---------------------------------------------------------------------------
# 2: 通用对话流式帧契约（/api/chat/stream）
# ---------------------------------------------------------------------------


class TestChatStreamContract:
    def test_tokens_and_done(self, monkeypatch):
        chunks = _run_chat_route(monkeypatch, message="你好")
        state = frontend_parse_chat_stream(chunks)

        assert state["tokens"] == "你好，世界"
        assert state["error"] is None
        assert chunks[-1] == "data: [DONE]\n\n"
        print("[PASS] /api/chat/stream 正文帧被前端正确拼接")

    def test_error_frame_is_not_rendered_as_answer(self, monkeypatch):
        """历史缺陷：会话越权时后端把"无权访问该会话"当普通 token 发出，
        前端照单全收渲染成模型回答 —— 用户以为模型答非所问。
        """
        chunks = _run_chat_route(
            monkeypatch, message="你好", conversation_id=9,
            verify_error=ValueError("not owner"),
        )
        state = frontend_parse_chat_stream(chunks)

        assert state["error"] == "无权访问该会话"
        assert state["tokens"] == "", "错误不能被拼进回答正文"
        print(f"[PASS] 会话越权走 error 控制帧: {state['error']}")



# ---------------------------------------------------------------------------
# 3: 上传响应契约（/api/documents/upload，Phase 3 §5.3）
# ---------------------------------------------------------------------------


class _RecordingWorker:
    """只记录不执行：真实 LocalWorker 会起线程跑解析/嵌入，测试不该碰。"""

    def __init__(self):
        self.tasks: list = []

    def submit(self, task):
        self.tasks.append(task)
        return task.task_id


def _seed_user_and_kb(temp_db) -> tuple[int, int]:
    """在临时库里造一个用户 + 知识库（不依赖注册接口，避免 JWT/限流/真实库）。"""
    from app.models.knowledge_base import KnowledgeBase
    from app.models.user import User

    async def _seed():
        async with temp_db.session() as session:
            user = User(
                username="contract_user",
                email="contract_user@example.com",
                password_hash="not-used",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            kb = KnowledgeBase(name="前端契约知识库", user_id=user.id)
            session.add(kb)
            await session.commit()
            await session.refresh(kb)
            return user.id, kb.id

    return asyncio.run(_seed())


class _AuthUser:
    """``get_current_user`` 替身（路由只用到 id/username）。"""

    def __init__(self, user_id: int, username: str = "contract_user"):
        self.id = user_id
        self.username = username


class TestUploadResponseContract:
    def _prepare(self, temp_db, tmp_path, monkeypatch, client):
        """把上传链路固定到临时库/临时目录，并让后台 Worker 只记录不执行。

        真实 LocalWorker 会起线程跑解析 + 嵌入（还会写**真实**向量库），
        测试必须替换掉它；同时按路由实际引用的 ``get_db`` 覆盖依赖，
        否则 reload 过的模块会让请求落到开发库（见 conftest.client 注释）。
        """
        from app.api import documents as documents_api
        from app.auth.deps import get_current_user
        from app.main import app
        from app.services import tasks as tasks_pkg

        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        monkeypatch.setattr(settings, "DOCUMENT_DEDUP_ENABLED", True)
        monkeypatch.setattr(settings, "DOCUMENT_PROCESSING_ASYNC", True)

        worker = _RecordingWorker()
        monkeypatch.setattr(tasks_pkg, "_worker_instance", worker)

        user_id, kb_id = _seed_user_and_kb(temp_db)

        async def _override_get_db():
            async with temp_db.session() as session:
                yield session

        monkeypatch.setitem(
            app.dependency_overrides, documents_api.get_db, _override_get_db
        )
        monkeypatch.setitem(
            app.dependency_overrides, get_current_user, lambda: _AuthUser(user_id)
        )
        return worker, kb_id

    def test_dedupe_skips_and_dispatches_nothing(
        self, client, temp_db, tmp_path, monkeypatch
    ):
        """上传响应必须给出前端 UploadResult 需要的全部字段，
        且同内容第二次上传既不复用新记录、也不派发处理任务。"""
        worker, kb_id = self._prepare(temp_db, tmp_path, monkeypatch, client)

        content = b"phase 3 frontend contract: identical bytes\n"
        first = client.post(
            "/api/documents/upload",
            params={"knowledge_base_id": kb_id},
            files={"file": ("contract.txt", content, "text/plain")},
        )
        assert first.status_code in (200, 201), first.text
        body = first.json()
        assert set(body) >= {
            "message", "document_id", "filename", "status", "skipped", "duplicated_of",
        }, body
        assert body["skipped"] is False
        assert body["duplicated_of"] is None
        # 前端 Document.status 的联合类型必须包含 pending（真实上传后就是 pending）
        assert body["status"] == "pending", body["status"]
        assert len(worker.tasks) == 1, "新上传应派发一次处理任务"

        second = client.post(
            "/api/documents/upload",
            params={"knowledge_base_id": kb_id},
            files={"file": ("copy-of-contract.txt", content, "text/plain")},
        )
        assert second.status_code in (200, 201), second.text
        dup = second.json()
        assert dup["skipped"] is True, "同知识库同内容必须被跳过"
        assert dup["duplicated_of"] == body["document_id"]
        assert dup["document_id"] == body["document_id"], "复用既有记录而不是新建"
        assert "跳过" in dup["message"], dup["message"]
        assert len(worker.tasks) == 1, "幂等命中不得再派发处理任务"

        listed = client.get(
            "/api/documents", params={"knowledge_base_id": kb_id}
        ).json()
        assert listed["total"] == 1, "同内容只应留下一条记录（前端不会看到幽灵条目）"
        assert listed["documents"][0]["status"] == "pending"
        assert "retry_count" in listed["documents"][0]
        print(
            f"[PASS] 上传契约: skipped={dup['skipped']}, "
            f"duplicated_of={dup['duplicated_of']}, tasks={len(worker.tasks)}"
        )



# ---------------------------------------------------------------------------
# 4: Schema 字段契约（前端 TS 接口的镜像）
# ---------------------------------------------------------------------------


class TestSchemaContractMatchesFrontendTypes:
    def test_query_response_fields(self):
        from app.schemas.chat import QueryResponse, SourceReference

        assert set(QueryResponse.model_fields) >= {
            "answer", "sources", "citations", "has_knowledge",
            "abstained", "abstention_reason", "error",
        }
        assert set(SourceReference.model_fields) >= {
            "document_id", "filename", "chunk_index", "text", "page", "section",
        }
        print("[PASS] QueryResponse/SourceReference 字段覆盖前端 QueryAnswer")

    def test_upload_and_document_fields(self):
        from app.schemas.document import DocumentResponse, UploadResponse

        assert set(UploadResponse.model_fields) >= {
            "message", "document_id", "filename", "status", "skipped", "duplicated_of",
        }
        assert "retry_count" in DocumentResponse.model_fields, "§5.2 重试次数要对前端可见"
        print("[PASS] UploadResponse/DocumentResponse 字段覆盖前端 UploadResult")

    def test_citation_payload_fields(self):
        from app.services.citation.models import Citation

        payload = Citation(
            document_id="doc-1", filename="manual.pdf", chunk_id=0, score=0.5
        ).to_dict()
        assert set(payload) >= {
            "document_id", "filename", "chunk_id", "score", "page", "section", "display",
        }
        print("[PASS] Citation.to_dict 字段覆盖前端 Citation 接口")

    def test_document_status_values(self):
        from app.models.document import DocumentStatus

        values = {status.value for status in DocumentStatus}
        assert values >= {"pending", "processing", "completed", "failed"}, values
        print(f"[PASS] 文档状态取值: {sorted(values)}")

    def test_abstention_reason_codes(self):
        """前端 ChatMessage 的原因码文案表必须与后端取值一一对应。"""
        from app.services.retrieval.abstention import AbstentionReason

        assert {
            AbstentionReason.NO_CONTEXT,
            AbstentionReason.INSUFFICIENT_CONTEXT,
            AbstentionReason.LOW_RETRIEVAL_SCORE,
            AbstentionReason.LOW_RERANK_SCORE,
        } == {
            "no_context",
            "insufficient_context",
            "low_retrieval_score",
            "low_rerank_score",
        }
        print("[PASS] 拒答原因码与前端文案表一致")


# ---------------------------------------------------------------------------
# 5: 统一错误信封（前端 extractErrorMessage 的输入）
# ---------------------------------------------------------------------------


class TestErrorEnvelopeContract:
    def test_app_error_envelope_has_top_level_message(self):
        from app.core.exceptions import AppError, app_error_handler

        response = asyncio.run(
            app_error_handler(None, AppError("RATE_LIMITED", "请求过于频繁，请稍后重试", 429))
        )
        assert response.status_code == 429
        body = json.loads(response.body)
        assert set(body) == {"code", "message"}, body
        assert body["message"], "前端 extractErrorMessage 首选顶层 message（旧代码只读 detail）"
        print(f"[PASS] AppError 信封: code={body['code']}")

    def test_http_exception_envelope_has_top_level_message(self):
        from fastapi import HTTPException

        from app.core.exceptions import http_exception_handler

        response = asyncio.run(
            http_exception_handler(None, HTTPException(status_code=404, detail="无权访问该知识库"))
        )
        body = json.loads(response.body)
        assert body["message"] == "无权访问该知识库"
        assert body["code"] == "HTTP_ERROR"
        print("[PASS] HTTPException 信封同样带顶层 message")

