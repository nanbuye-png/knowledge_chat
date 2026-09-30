"""启动期安全配置测试 —— 审计 §6.1。

审计原文（docs/KNOWLEDGE_CHAT_REALITY_AUDIT.md §6.1）：
    1) [P0 安全] SECRET_KEY 默认公开值（core/config.py:124 =
       "knowledge-chat-secret-key-change-in-production"），.env.production 与
       compose 也是占位串 → 按仓库现状部署，任何人都可签发 ROOT token
    7) [暴露面] /docs、/redoc、/openapi.json 未按 ENVIRONMENT 关闭

覆盖四件事：

1. 生产环境 + 占位/短 SECRET_KEY → **拒绝启动**（用真实 lifespan 验证，
   而不是只调函数：函数写对了但调用点忘了接，测试照样绿）；
2. 生产环境 + 足够强的 SECRET_KEY → 放行；
3. 开发环境沿用默认值：只告警不阻断（本地开箱可用）；
4. /docs 暴露面随 ENVIRONMENT 关闭，且 ``ENABLE_API_DOCS`` 可显式覆盖。
"""

import pytest
from starlette.testclient import TestClient

from app.core.config import DEFAULT_SECRET_KEY, Settings, settings
from app.main import _api_docs_kwargs, app

STRONG_SECRET_KEY = "9f2c8b1e4a7d6f30c5b8e2a1947d3f60ce1b8a52d47f9031c6e5b2a8d47f0193"
WEAK_SECRET_KEY = "short-not-enough"


# ---------------------------------------------------------------------------
# 1 & 2 & 3：SECRET_KEY 自检
# ---------------------------------------------------------------------------


class TestSecretKeyFailFast:
    def test_placeholder_secret_key_is_rejected_in_production(self, monkeypatch):
        """生产环境必须拒绝启动（fail-fast），且错误信息要能指导修复。"""
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)

        with pytest.raises(RuntimeError) as excinfo:
            settings.assert_secure_config()

        message = str(excinfo.value)
        assert "SECRET_KEY" in message
        assert "openssl rand -hex 32" in message, "报错必须给出可执行的修复方式"
        print(f"[PASS] 生产 + 占位 SECRET_KEY → 拒绝启动：{message[:60]}…")

    def test_short_secret_key_is_rejected_in_production(self, monkeypatch):
        """占位串之外，短密钥同样不能上生产（熵不足）。"""
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "SECRET_KEY", WEAK_SECRET_KEY)

        with pytest.raises(RuntimeError, match="太短"):
            settings.assert_secure_config()

    def test_empty_secret_key_is_rejected_in_production(self, monkeypatch):
        """.env.production 里最常见的状态：变量在、值为空。"""
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "SECRET_KEY", "")

        with pytest.raises(RuntimeError, match="为空"):
            settings.assert_secure_config()

    def test_strong_secret_key_passes_in_production(self, monkeypatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "SECRET_KEY", STRONG_SECRET_KEY)

        assert settings.assert_secure_config() == []
        print("[PASS] 生产 + openssl rand -hex 32 → 自检通过")

    def test_development_keeps_working_with_default_key(self, monkeypatch):
        """开发环境不能因为自检而开不了机：只返回问题，交给调用方告警。"""
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)

        problems = settings.assert_secure_config()
        assert problems, "默认密钥必须被识别为问题（否则告警也不会打印）"
        assert "占位值" in problems[0]

    def test_app_refuses_to_start_in_production(self, monkeypatch):
        """端到端：真实 lifespan 下应用起不来（而不是只有函数会抛）。"""
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "SECRET_KEY", DEFAULT_SECRET_KEY)

        with pytest.raises(RuntimeError, match="拒绝启动"):
            with TestClient(app):
                pass
        print("[PASS] TestClient(app) 启动即失败（lifespan 已接线）")


# ---------------------------------------------------------------------------
# 4：/docs 暴露面
# ---------------------------------------------------------------------------


class TestApiDocsExposure:
    def test_production_turns_docs_off(self):
        kwargs = _api_docs_kwargs(Settings(ENVIRONMENT="production"))
        assert kwargs == {"docs_url": None, "redoc_url": None, "openapi_url": None}
        print("[PASS] production → /docs、/redoc、/openapi.json 全关")

    def test_development_keeps_docs_on(self):
        kwargs = _api_docs_kwargs(Settings(ENVIRONMENT="development"))
        assert kwargs["docs_url"] == "/docs"
        assert kwargs["redoc_url"] == "/redoc"

    def test_explicit_switch_overrides_environment(self):
        """显式打开只应在受控调试时使用，所以要能被显式打开（否则会有人去改代码）。"""
        assert Settings(ENVIRONMENT="production", ENABLE_API_DOCS=True).docs_enabled
        assert not Settings(ENVIRONMENT="development", ENABLE_API_DOCS=False).docs_enabled

    def test_running_app_still_serves_docs_in_development(self, client):
        """当前测试环境是 development：/docs 必须可用，别把开发体验一起关掉。"""
        assert settings.ENVIRONMENT == "development"
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
