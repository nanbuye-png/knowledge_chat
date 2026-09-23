"""LLM 配置测试 — 校验 agnes-2.5-flash 的配置自检、Provider 装配与输出规范化。

覆盖范围：
1. ``Settings.check_llm_config()``：Provider / 模型名前缀 / API Key 的一致性校验。
2. ``LLMProviderFactory``：agens Provider 是否使用配置中的 *agnes-2.5-flash*。
3. ``AgensProvider``：推理型模型（先 ``reasoning_content`` 后正文）的输出规范化。

Run: cd backend && python -m pytest tests/test_llm_config.py -v
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import (
    _BACKEND_DIR,
    KNOWN_MODELS,
    PROVIDER_MODEL_PREFIXES,
    Settings,
)
from app.services.llm.agens_provider import AgensProvider
from app.services.llm.factory import LLMProviderFactory

AGNES_MODEL = "agnes-2.5-flash"
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agens_settings(**overrides) -> Settings:
    """构造一份默认使用 agnes-2.5-flash 的配置。"""
    values = {
        "LLM_PROVIDER": "agens",
        "LLM_MODEL": AGNES_MODEL,
        "AGENS_API_KEY": "sk-test-agens-key",
        "AGENS_API_BASE": AGNES_BASE_URL,
    }
    values.update(overrides)
    return Settings(**values)


class _Delta:
    """模拟流式 chunk 中的 delta（同时含 content 与 reasoning_content）。"""

    def __init__(self, content=None, reasoning_content=None):
        self.content = content
        self.reasoning_content = reasoning_content


class _Choice:
    def __init__(self, delta):
        self.delta = delta


class _Chunk:
    def __init__(self, delta):
        self.choices = [_Choice(delta)]


class _EmptyChoicesChunk:
    """模拟 OpenAI 兼容接口中偶尔出现的空 choices 心跳包。"""

    def __init__(self):
        self.choices = []


class _FakeStream:
    """可异步迭代的假流对象，带 close() 以模拟真实 SDK。"""

    def __init__(self, chunks):
        self._chunks = chunks
        self.closed = False

    async def _generator(self):
        for chunk in self._chunks:
            yield chunk

    def __aiter__(self):
        return self._generator()

    def close(self):
        self.closed = True


def _async_return(value):
    """构造一个 await 后返回 *value* 的异步函数。"""

    async def _coro(*args, **kwargs):
        return value

    return _coro


def _provider_with_stream(chunks) -> AgensProvider:
    """返回一个使用假流对象的 AgensProvider。"""
    provider = AgensProvider("k", AGNES_BASE_URL, AGNES_MODEL)
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=_async_return(_FakeStream(chunks)))
        )
    )
    return provider


def _provider_with_response(content) -> AgensProvider:
    """返回一个使用假非流式响应的 AgensProvider。"""
    message = SimpleNamespace(content=content)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    provider = AgensProvider("k", AGNES_BASE_URL, AGNES_MODEL)
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=_async_return(response))
        )
    )
    return provider


def _collect_stream(provider: AgensProvider) -> list[str]:
    """同步收集流式输出（与 ``test_agens_fix.py`` 保持一致的 asyncio.run 风格）。"""

    async def _run() -> list[str]:
        tokens: list[str] = []
        stream = await provider.chat([{"role": "user", "content": "hi"}], stream=True)
        async for token in stream:
            tokens.append(token)
        return tokens

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# 1. 配置自检
# ---------------------------------------------------------------------------


class TestLlmConfigCheck:
    """``Settings.check_llm_config()`` 的行为。"""

    def test_agnes_2_5_flash_is_a_known_model(self):
        """agnes-2.5-flash 应登记在 KNOWN_MODELS 中。"""
        assert AGNES_MODEL in KNOWN_MODELS["agens"]
        assert PROVIDER_MODEL_PREFIXES["agens"] == "agnes"

    def test_valid_agnes_config_has_no_issues(self):
        """LLM_PROVIDER=agens + agnes-2.5-flash + API Key 齐备 → 无告警。"""
        assert _agens_settings().check_llm_config() == []

    def test_valid_deepseek_config_has_no_issues(self):
        """DeepSeek 默认组合仍然自洽（回归保护）。"""
        settings = Settings(
            LLM_PROVIDER="deepseek",
            LLM_MODEL="deepseek-chat",
            DEEPSEEK_API_KEY="sk-test",
            DEEPSEEK_API_BASE="https://api.deepseek.com",
        )
        assert settings.check_llm_config() == []

    def test_provider_model_mismatch_is_reported(self):
        """agens Provider 搭配 deepseek 模型 → 报“不匹配”。"""
        issues = _agens_settings(LLM_MODEL="deepseek-chat").check_llm_config()
        assert any("不匹配" in issue for issue in issues)

    def test_unknown_agnes_model_is_reported(self):
        """未知的 agnes 模型名 → 提示不在已知模型列表。"""
        issues = _agens_settings(LLM_MODEL="agnes-9.9-turbo").check_llm_config()
        assert any("不在已知模型列表" in issue for issue in issues)

    def test_missing_agens_api_key_is_reported(self):
        """缺失 AGENS_API_KEY → 提示将返回 401。"""
        issues = _agens_settings(AGENS_API_KEY="").check_llm_config()
        assert any("AGENS_API_KEY" in issue for issue in issues)

    def test_missing_agens_api_base_is_reported(self):
        """缺失 AGENS_API_BASE → 提示无法定位接口地址。"""
        issues = _agens_settings(AGENS_API_BASE="").check_llm_config()
        assert any("AGENS_API_BASE" in issue for issue in issues)

    def test_unsupported_provider_is_reported(self):
        """不支持的 Provider → 提示可选值列表。"""
        issues = _agens_settings(LLM_PROVIDER="openai").check_llm_config()
        assert any("不受支持" in issue for issue in issues)

    def test_empty_model_is_reported(self):
        """LLM_MODEL 为空 → 提示无法确定模型名。"""
        issues = _agens_settings(LLM_MODEL="").check_llm_config()
        assert any("LLM_MODEL 为空" in issue for issue in issues)


class TestEnvFileRegression:
    """``backend/.env`` 的回归保护：启用 agens 时必须使用合法的 agnes 模型名。"""

    def test_env_file_model_matches_provider(self):
        env_file = _BACKEND_DIR / ".env"
        if not env_file.exists():
            pytest.skip("backend/.env 不存在，跳过环境配置回归检查")

        values: dict[str, str] = {}
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        if values.get("LLM_PROVIDER", "").strip().lower() != "agens":
            pytest.skip("backend/.env 未启用 agens Provider，跳过")

        model = values.get("LLM_MODEL", "").strip()
        assert model in KNOWN_MODELS["agens"], (
            f"backend/.env 的 LLM_MODEL='{model}' 不是合法的 agnes 模型"
        )
        assert values.get("AGENS_API_KEY", "").strip(), "backend/.env 缺少 AGENS_API_KEY"
        assert values.get("AGENS_API_BASE", "").strip(), "backend/.env 缺少 AGENS_API_BASE"


# ---------------------------------------------------------------------------
# 2. Provider 装配
# ---------------------------------------------------------------------------


class TestFactoryUsesConfiguredAgnesModel:
    """``LLMProviderFactory`` 应把配置中的模型名透传给 AgensProvider。"""

    def test_create_uses_llm_model_from_settings(self):
        provider = LLMProviderFactory.create(_agens_settings())

        assert isinstance(provider, AgensProvider)
        assert provider._model == AGNES_MODEL
        assert provider._base_url == AGNES_BASE_URL
        assert provider._api_key == "sk-test-agens-key"

    def test_create_with_name_uses_llm_model_from_settings(self):
        provider = LLMProviderFactory.create_with_name("agens", _agens_settings())

        assert isinstance(provider, AgensProvider)
        assert provider._model == AGNES_MODEL

    def test_create_from_model_uses_record_model_name(self):
        record = SimpleNamespace(provider="agens", model_name=AGNES_MODEL)

        provider = LLMProviderFactory.create_from_model(record, _agens_settings())

        assert isinstance(provider, AgensProvider)
        assert provider._model == AGNES_MODEL

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            LLMProviderFactory.create_with_name("openai", _agens_settings())


# ---------------------------------------------------------------------------
# 3. 推理型模型输出规范化
# ---------------------------------------------------------------------------


class TestAgensOutputNormalization:
    """agnes-2.5-flash 会先输出 reasoning_content，正文带前导换行，需要清理。"""

    def test_stream_strips_leading_newlines(self):
        chunks = [
            _EmptyChoicesChunk(),
            _Chunk(_Delta(content="", reasoning_content=None)),
            _Chunk(_Delta(content=None, reasoning_content="用户")),
            _Chunk(_Delta(content="\n\n")),
            _Chunk(_Delta(content="你好")),
            _Chunk(_Delta(content="，世界")),
        ]
        provider = _provider_with_stream(chunks)

        assert _collect_stream(provider) == ["你好", "，世界"]

    def test_stream_keeps_later_whitespace_chunks(self):
        """只裁剪首个正文 chunk 的前导空白，后续换行需保留（Markdown 段落）。"""
        chunks = [
            _Chunk(_Delta(content="\n\n第一段")),
            _Chunk(_Delta(content="\n\n第二段")),
        ]
        provider = _provider_with_stream(chunks)

        assert _collect_stream(provider) == ["第一段", "\n\n第二段"]

    def test_stream_without_leading_newlines_unchanged(self):
        chunks = [_Chunk(_Delta(content="Hello")), _Chunk(_Delta(content="!"))]
        provider = _provider_with_stream(chunks)

        assert _collect_stream(provider) == ["Hello", "!"]

    def test_non_stream_strips_leading_newlines(self):
        provider = _provider_with_response("\n\nRAG 是检索增强生成。")

        result = asyncio.run(
            provider.chat([{"role": "user", "content": "hi"}], stream=False)
        )
        assert result == "RAG 是检索增强生成。"

    def test_non_stream_none_content_returns_empty_string(self):
        provider = _provider_with_response(None)

        result = asyncio.run(
            provider.chat([{"role": "user", "content": "hi"}], stream=False)
        )
        assert result == ""

