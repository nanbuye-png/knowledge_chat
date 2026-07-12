"""Test script to verify AgensProvider compatibility (migrated to services/llm).

Run: cd backend && python -m pytest tests/test_agens_fix.py -v
"""

import asyncio
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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

    def test_factory_create_agens(self):
        """(a) LLMProviderFactory.create_with_name('agens') returns AgensProvider."""
        from app.services.llm.factory import LLMProviderFactory
        from app.core.config import Settings

        settings = Settings(
            LLM_PROVIDER="agens",
            AGENS_API_KEY="test-key",
            AGENS_API_BASE="https://api.agens.test",
            LLM_MODEL="agens-model",
        )
        provider = LLMProviderFactory.create_with_name("agens", settings)
        from app.services.llm.agens_provider import AgensProvider

        assert isinstance(provider, AgensProvider)

    def test_stream_skips_empty_choices(self):
        """(b) empty choices list → skip, no exception."""
        from app.services.llm.agens_provider import AgensProvider

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
            async for t in await provider.chat(
                [{"role": "user", "content": "hi"}], stream=True
            ):
                tokens.append(t)
            return tokens

        tokens = asyncio.run(_collect())
        assert tokens == ["Hello"]
        assert stream_mock.close.called

    def test_stream_skips_none_delta(self):
        """(b2) choice.delta is None → skip."""
        from app.services.llm.agens_provider import AgensProvider

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
            async for t in await provider.chat(
                [{"role": "user", "content": "hi"}], stream=True
            ):
                tokens.append(t)
            return tokens

        tokens = asyncio.run(_collect())
        assert tokens == ["Hello"]

    def test_stream_skips_no_delta_attr(self):
        """(b3) choice has no .delta attribute → skip."""
        from app.services.llm.agens_provider import AgensProvider

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
            async for t in await provider.chat(
                [{"role": "user", "content": "hi"}], stream=True
            ):
                tokens.append(t)
            return tokens

        tokens = asyncio.run(_collect())
        assert tokens == ["Hello"]

    def test_stream_skips_empty_content_string(self):
        """(b4) content is empty string → skip."""
        from app.services.llm.agens_provider import AgensProvider

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
            async for t in await provider.chat(
                [{"role": "user", "content": "hi"}], stream=True
            ):
                tokens.append(t)
            return tokens

        tokens = asyncio.run(_collect())
        assert tokens == ["Hello"]


class TestAgensStreamClose:
    """Verify stream.close() is handled correctly for both sync & async."""

    def test_sync_close_not_awaited(self):
        """(c1) Sync close (DeepSeek-style): no coroutine warning."""
        from app.services.llm.agens_provider import AgensProvider

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
                async for _ in await provider.chat(
                    [{"role": "user", "content": "hi"}], stream=True
                ):
                    pass

            asyncio.run(_run())

        coro_warnings = [
            x
            for x in w
            if issubclass(x.category, RuntimeWarning)
            and "never awaited" in str(x.message).lower()
        ]
        assert not coro_warnings, (
            f"Got coroutine warning: {[str(x.message) for x in coro_warnings]}"
        )
        assert stream_mock.close.called

    def test_async_close_awaited(self):
        """(c2) Async close (Agens AsyncStream): properly awaited."""
        from app.services.llm.agens_provider import AgensProvider

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
                async for _ in await provider.chat(
                    [{"role": "user", "content": "hi"}], stream=True
                ):
                    pass

            asyncio.run(_run())

        coro_warnings = [
            x
            for x in w
            if issubclass(x.category, RuntimeWarning)
            and "never awaited" in str(x.message).lower()
        ]
        assert not coro_warnings, (
            f"Got coroutine warning: {[str(x.message) for x in coro_warnings]}"
        )
        assert stream_mock.close.called


class TestAgensChatSafety:
    """Verify chat() method protects against empty choices."""

    def test_chat_returns_content_or_empty_string(self):
        """Chat returns content, or '' if content is None."""
        from app.services.llm.agens_provider import AgensProvider

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

        result = asyncio.run(
            provider.chat([{"role": "user", "content": "hi"}], stream=False)
        )
        assert result == ""


class TestDeepSeekUnaffected:
    """DeepSeek Provider behavior remains unchanged."""

    def test_deepseek_still_works(self):
        """DeepSeek provider can be created via factory."""
        from app.services.llm.factory import LLMProviderFactory
        from app.core.config import Settings

        settings = Settings(
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="test-key",
            DEEPSEEK_API_BASE="https://api.deepseek.com",
            LLM_MODEL="deepseek-chat",
        )
        provider = LLMProviderFactory.create(settings)
        from app.services.llm.deepseek_provider import DeepSeekProvider

        assert isinstance(provider, DeepSeekProvider)