"""Tests for general chat message persistence (AI 对话消息落库).

Covers:
    - ChatRequest.conversation_id schema field
    - conversation title helpers (generate / auto update)
    - /api/chat/stream persisting user + assistant messages

Run: cd backend && ..\\.venv\\Scripts\\python.exe -m pytest tests/test_chat_persistence.py -v
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, ".")

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeResult:
    """Minimal stand-in for a SQLAlchemy Result object."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeConversation:
    def __init__(self, title):
        self.title = title


class _FakeSessionContext:
    """Async context manager yielding a (fake) AsyncSession."""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _run_stream(request, *, stream_fn=None, create_user_error=None, verify_error=None):
    """Call the /api/chat/stream endpoint with everything mocked out.

    Returns (saved, chunks) where ``saved`` collects persisted messages.
    """
    from app.api import chat as chat_api

    saved = {"user": [], "assistant": []}
    db = MagicMock()

    async def default_stream(message, history=None):
        yield "你好"
        yield "，世界"

    async def fake_create_user_message(_db, conversation_id, content):
        if create_user_error is not None:
            raise create_user_error
        saved["user"].append((conversation_id, content))
        return {}

    async def fake_create_assistant_message(_db, conversation_id, content):
        saved["assistant"].append((conversation_id, content))
        return {}

    async def fake_verify(_db, conversation_id, user_id):
        if verify_error is not None:
            raise verify_error
        return MagicMock()

    async def _run():
        with patch.object(chat_api.chat_service, "stream_chat", stream_fn or default_stream), \
             patch.object(chat_api, "async_session", lambda: _FakeSessionContext(db)), \
             patch.object(chat_api, "update_user_activity", AsyncMock()), \
             patch.object(chat_api, "_verify_conversation_ownership", fake_verify), \
             patch.object(chat_api, "auto_update_conversation_title", AsyncMock()), \
             patch.object(chat_api, "create_user_message", fake_create_user_message), \
             patch.object(chat_api, "create_assistant_message", fake_create_assistant_message):
            response = await chat_api.stream_chat(request, current_user=MagicMock(id=1))
            return [chunk async for chunk in response.body_iterator]

    return saved, asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests — Part 1: schema
# ---------------------------------------------------------------------------

class TestChatRequestSchema:
    def test_conversation_id_defaults_to_none(self):
        from app.schemas.chat import ChatRequest

        assert ChatRequest(message="hi").conversation_id is None

    def test_accepts_conversation_id(self):
        from app.schemas.chat import ChatRequest

        assert ChatRequest(message="hi", conversation_id=42).conversation_id == 42


# ---------------------------------------------------------------------------
# Tests — Part 2: conversation title helpers
# ---------------------------------------------------------------------------

class TestGenerateConversationTitle:
    def test_strips_whitespace(self):
        from app.services.conversation_service import generate_conversation_title

        assert generate_conversation_title("  你好世界  ") == "你好世界"

    def test_truncates_to_max_length(self):
        from app.services.conversation_service import generate_conversation_title

        assert generate_conversation_title("a" * 50) == "a" * 30
        assert generate_conversation_title("abcdefg", max_length=3) == "abc"


class TestAutoUpdateConversationTitle:
    def test_updates_when_title_is_default(self):
        from app.services import conversation_service as cs

        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult(_FakeConversation("New Chat")))

        with patch.object(cs, "update_conversation_title", AsyncMock()) as mock_update:
            asyncio.run(cs.auto_update_conversation_title(db, 5, "  帮我总结文档  "))

        mock_update.assert_awaited_once()
        assert mock_update.await_args.args[1] == 5
        assert mock_update.await_args.args[2] == "帮我总结文档"

    def test_keeps_custom_title(self):
        from app.services import conversation_service as cs

        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult(_FakeConversation("我的会话")))

        with patch.object(cs, "update_conversation_title", AsyncMock()) as mock_update:
            asyncio.run(cs.auto_update_conversation_title(db, 5, "帮我总结文档"))

        mock_update.assert_not_awaited()

    def test_missing_conversation_is_noop(self):
        from app.services import conversation_service as cs

        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult(None))

        with patch.object(cs, "update_conversation_title", AsyncMock()) as mock_update:
            asyncio.run(cs.auto_update_conversation_title(db, 999, "hi"))

        mock_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests — Part 3: /api/chat/stream persistence
# ---------------------------------------------------------------------------

class TestStreamChatPersistence:
    def test_saves_user_and_assistant_messages(self):
        from app.schemas.chat import ChatRequest

        saved, chunks = _run_stream(ChatRequest(message="你好", conversation_id=7))

        assert saved["user"] == [(7, "你好")]
        assert saved["assistant"] == [(7, "你好，世界")]
        assert chunks[-1] == "data: [DONE]\n\n"

    def test_no_conversation_id_saves_nothing(self):
        from app.schemas.chat import ChatRequest

        saved, chunks = _run_stream(ChatRequest(message="你好"))

        assert saved["user"] == []
        assert saved["assistant"] == []
        assert chunks[-1] == "data: [DONE]\n\n"

    def test_stream_failure_does_not_save_assistant_message(self):
        from app.schemas.chat import ChatRequest

        async def failing_stream(message, history=None):
            yield "部分内容"
            raise RuntimeError("provider down")

        saved, chunks = _run_stream(
            ChatRequest(message="你好", conversation_id=7), stream_fn=failing_stream
        )

        assert saved["user"] == [(7, "你好")]
        assert saved["assistant"] == []
        assert any("内部错误" in chunk for chunk in chunks)

    def test_foreign_conversation_is_rejected_before_calling_llm(self):
        from app.schemas.chat import ChatRequest

        stream_mock = MagicMock()
        saved, chunks = _run_stream(
            ChatRequest(message="你好", conversation_id=9),
            stream_fn=stream_mock,
            verify_error=ValueError("not owner"),
        )

        stream_mock.assert_not_called()
        assert saved["user"] == []
        assert saved["assistant"] == []
        assert any("无权访问该会话" in chunk for chunk in chunks)

    def test_message_save_failure_stops_streaming(self):
        from app.schemas.chat import ChatRequest

        stream_mock = MagicMock()
        saved, chunks = _run_stream(
            ChatRequest(message="你好", conversation_id=7),
            stream_fn=stream_mock,
            create_user_error=RuntimeError("db down"),
        )

        stream_mock.assert_not_called()
        assert saved["assistant"] == []
        assert any("消息保存失败" in chunk for chunk in chunks)
