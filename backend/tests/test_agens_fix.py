"""Test script to verify AgensProvider stream-chat compatibility fixes.

Run: cd backend && python -m pytest tests/test_agens_fix.py -v
"""

import asyncio
import sys
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, ".")


# ---------------------------------------------------------------------------
# Safe-value mocks
# ---------------------------------------------------------------------------

_MOCK_CHOICE_WITH_CONTENT = MagicMock()
_DELTA_WITH_CONTENT = MagicMock(content="Hello")
_MOCK_CHOICE_WITH_CONTENT.delta = _DELTA_WITH_CONTENT


_MOCK_CHOICE_EMPTY_CONTENT = MagicMock()
_DELTA_EMPTY_CONTENT = MagicMock(content="")
_MOCK_CHOICE_EMPTY_CONTENT.delta = _DELTA_EMPTY_CONTENT


_MOCK_CHOICE_NO_DELTA = MagicMock(spec=[])  # no .delta attribute
del _MOCK_CHOICE_NO_DELTA.delta  # ensure AttributeError on getattr w/ default


# Object that has .delta = None
_MOCK_CHOICE_NONE_DELTA = MagicMock()
_MOCK_CHOICE_NONE_DELTA.delta = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgensStreamChatSafeAccess:
    """Verify stream_chat handles every edge-case chunk safely."""

    def test_get_llm_provider_agens(self):
        """(a) get_llm_provider('agens') returns AgensProvider."""
        from app.providers.factory import get_llm_provider

        with patch(
            "app.core.config.settings.AGENS_API_KEY", "test-key"
        ), patch(
            "app.core.config.settings.AGENS_API_BASE", "https://api.agens.test"
        ), patch(
            "app.core.config.settings.LLM_MODEL", "agens-model"
        ):
            provider = get_llm_provider("agens")
            from app.providers.agens import AgensProvider

            assert isinstance(provider, AgensProvider)

    def test_stream_skips_empty_choices(self):
        """(b) empty choices list → skip, no exception."""
        from app.providers.agens import AgensProvider

        provider = AgensProvider("k", "https://a", "m")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock()

        # Build a fake async iterable with an empty-choices chunk
        stream_mock = MagicMock()

        chunk_no_choices = MagicMock()
        chunk_no_choices.choices = []

        chunk_good = MagicMock()
        chunk_good.choices = [_MOCK_CHOICE_WITH_CONTENT]

        async def _fake_stream():
            yield chunk_no_choices
            yield chunk_good

        stream_mock.__aiter__ = lambda s: _fake_stream()
        stream_mock.close = MagicMock()

        provider._client.chat.completions.create.return_value = stream_mock

        async def _collect():
            tokens = []
            async for t in provider.stream_chat([{"role": "user", "content": "hi"}]):
                tokens.append(t)
            return tokens

        tokens = asyncio.run(_collect())
        assert tokens == ["Hello"]
        assert stream_mock.close.called

    def test_stream_skips_none_delta(self):
        """(b2) choice.delta is None → skip."""
        from app.providers.agens import AgensProvider

        provider = AgensProvider("k", "https://a", "m")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock()

        stream_mock = MagicMock()
        chunk_none_delta = MagicMock()
        chunk_none_delta.choices = [_MOCK_CHOICE_NONE_DELTA]
        chunk_good = MagicMock()
        chunk_good.choices = [_MOCK_CHOICE_WITH_CONTENT]

        async def _fake_stream():
            yield chunk_none_delta
            yield chunk_good

        stream_mock.__aiter__ = lambda s: _fake_stream()
        stream_mock.close = MagicMock()
        provider._client.chat.completions.create.return_value = stream_mock

        async def _collect():
            tokens = []
            async for t in provider.stream_chat([{"role": "user", "content": "hi"}]):
                tokens.append(t)
            return tokens

        tokens = asyncio.run(_collect())
        assert tokens == ["Hello"]

    def test_stream_skips_no_delta_attr(self):
        """(b3) choice has no .delta attribute → skip."""
        from app.providers.agens import AgensProvider

        provider = AgensProvider("k", "https://a", "m")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock()

        stream_mock = MagicMock()
        chunk_no_delta = MagicMock()
        chunk_no_delta.choices = [_MOCK_CHOICE_NO_DELTA]
        chunk_good = MagicMock()
        chunk_good.choices = [_MOCK_CHOICE_WITH_CONTENT]

        async def _fake_stream():
            yield chunk_no_delta
            yield chunk_good

        stream_mock.__aiter__ = lambda s: _fake_stream()
        stream_mock.close = MagicMock()
        provider._client.chat.completions.create.return_value = stream_mock

        async def _collect():
            tokens = []
            async for t in provider.stream_chat([{"role": "user", "content": "hi"}]):
                tokens.append(t)
            return tokens

        tokens = asyncio.run(_collect())
        assert tokens == ["Hello"]

    def test_stream_skips_empty_content_string(self):
        """(b4) content is empty string → skip."""
        from app.providers.agens import AgensProvider

        provider = AgensProvider("k", "https://a", "m")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock()

        stream_mock = MagicMock()
        chunk_empty = MagicMock()
        chunk_empty.choices = [_MOCK_CHOICE_EMPTY_CONTENT]
        chunk_good = MagicMock()
        chunk_good.choices = [_MOCK_CHOICE_WITH_CONTENT]

        async def _fake_stream():
            yield chunk_empty
            yield chunk_good

        stream_mock.__aiter__ = lambda s: _fake_stream()
        stream_mock.close = MagicMock()
        provider._client.chat.completions.create.return_value = stream_mock

        async def _collect():
            tokens = []
            async for t in provider.stream_chat([{"role": "user", "content": "hi"}]):
                tokens.append(t)
            return tokens

        tokens = asyncio.run(_collect())
        assert tokens == ["Hello"]


class TestAgensStreamClose:
    """Verify stream.close() is handled correctly for both sync & async."""

    def test_sync_close_not_awaited(self):
        """(c1) Sync close (DeepSeek-style): no coroutine warning."""
        from app.providers.agens import AgensProvider

        provider = AgensProvider("k", "https://a", "m")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock()

        stream_mock = MagicMock()
        stream_mock.close = MagicMock(return_value=None)  # sync

        async def _fake_stream():
            yield MagicMock(choices=[_MOCK_CHOICE_WITH_CONTENT])

        stream_mock.__aiter__ = lambda s: _fake_stream()
        provider._client.chat.completions.create.return_value = stream_mock

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            async def _run():
                async for _ in provider.stream_chat([{"role": "user", "content": "hi"}]):
                    pass

            asyncio.run(_run())

        coro_warnings = [
            x for x in w
            if issubclass(x.category, RuntimeWarning)
            and "never awaited" in str(x.message).lower()
        ]
        assert not coro_warnings, (
            f"Got coroutine warning: {[str(x.message) for x in coro_warnings]}"
        )
        assert stream_mock.close.called

    def test_async_close_awaited(self):
        """(c2) Async close (Agens AsyncStream): properly awaited."""
        from app.providers.agens import AgensProvider

        provider = AgensProvider("k", "https://a", "m")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock()

        async def _async_close():
            pass

        stream_mock = MagicMock()
        stream_mock.close = MagicMock(return_value=_async_close())  # coroutine

        async def _fake_stream():
            yield MagicMock(choices=[_MOCK_CHOICE_WITH_CONTENT])

        stream_mock.__aiter__ = lambda s: _fake_stream()
        provider._client.chat.completions.create.return_value = stream_mock

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            async def _run():
                async for _ in provider.stream_chat([{"role": "user", "content": "hi"}]):
                    pass

            asyncio.run(_run())

        coro_warnings = [
            x for x in w
            if issubclass(x.category, RuntimeWarning)
            and "never awaited" in str(x.message).lower()
        ]
        assert not coro_warnings, (
            f"Got coroutine warning: {[str(x.message) for x in coro_warnings]}"
        )
        assert stream_mock.close.called


class TestAgensChatSafety:
    """Verify chat() method protects against empty choices."""

    def test_chat_empty_choices_raises(self):
        """(3) chat() with empty choices raises ValueError."""
        from app.providers.agens import AgensProvider

        provider = AgensProvider("k", "https://a", "m")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock()

        response_mock = MagicMock()
        response_mock.choices = []
        provider._client.chat.completions.create.return_value = response_mock

        with pytest.raises(ValueError, match="empty choices"):
            asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))

    def test_chat_returns_content_or_empty_string(self):
        """(3) chat() returns content, or '' if content is None."""
        from app.providers.agens import AgensProvider

        provider = AgensProvider("k", "https://a", "m")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock()

        response_mock = MagicMock()
        msg_mock = MagicMock()
        msg_mock.content = None
        choice_mock = MagicMock()
        choice_mock.message = msg_mock
        response_mock.choices = [choice_mock]
        provider._client.chat.completions.create.return_value = response_mock

        result = asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))
        assert result == ""


class TestDeepSeekUnaffected:
    """(d) DeepSeek Provider behavior remains unchanged."""

    def test_deepseek_still_works(self):
        """DeepSeek provider can be created and has stream capability."""
        from app.providers.factory import get_llm_provider

        with patch(
            "app.core.config.settings.DEEPSEEK_API_KEY", "test-key"
        ), patch(
            "app.core.config.settings.DEEPSEEK_API_BASE", "https://api.deepseek.com"
        ), patch(
            "app.core.config.settings.LLM_MODEL", "deepseek-chat"
        ):
            provider = get_llm_provider("deepseek")
            from app.providers.deepseek import DeepSeekProvider

            assert isinstance(provider, DeepSeekProvider)
            assert provider.capabilities.supports_stream is True