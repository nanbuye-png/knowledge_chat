"""Phase 3 §5.4 限流统一后的回归测试。

审计 §5.4 的三个问题在这里被锁定：

1. **三套实现**：只剩一个入口 ``security.rate_limiter.check_rate_limit``，
   Redis 优先、进程内滑动窗口兜底（``services/rate_limit_service`` 变成门面）。
2. **X-Forwarded-For 伪造**：客户端可以伪造最左侧字段绕过限流；
   现在按 ``TRUSTED_PROXY_COUNT`` 从右往左取信任值。
3. **/stream 绕过限流**：``/api/chat/stream`` 与 ``/api/knowledge/query/stream``
   现在带路由级突发限额；用户维度改由中间件解析 JWT 得到
   （此前 ``request.state.user_id`` 从来没人赋值）。
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.net import client_ip  # noqa: E402
from app.services.security.rate_limiter import check_rate_limit  # noqa: E402


def _patch_settings(monkeypatch, **values) -> None:
    """把配置写到"所有持有 settings 引用的 app 模块"上，而不只是本模块收集期拿到的那份。

    为什么必须这样：``test_connection_pool`` / ``test_db_migration`` /
    ``test_provider_factory`` 会 ``importlib.reload(app.core.config)``，而 config.py
    在模块级执行 ``settings = Settings()`` —— 每 reload 一次就换一个新的 Settings 对象。
    于是"收集期被 import 的模块"（如 ``app.core.net``、本测试模块）和"运行期才被
    import 的模块"（如 ``app.core.rate_limit``：把 settings 绑成模块级引用、请求时才
    ``getattr``）手里各是一份不同的对象。只改本模块那份，真正生效的那份还是默认
    20 次/分钟 —— 表现为"整包跑第二次请求不是 429，单独跑这个文件却全绿"。
    """
    targets: dict[int, object] = {}
    for module in list(sys.modules.values()):
        if not getattr(module, "__name__", "").startswith("app."):
            continue
        candidate = getattr(module, "settings", None)
        if candidate is not None:
            targets.setdefault(id(candidate), candidate)

    for target in targets.values():
        for name, value in values.items():
            if hasattr(target, name):
                monkeypatch.setattr(target, name, value)


class _FakeRequest:
    def __init__(self, headers=None, client_host="127.0.0.1"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": client_host})()


class _FakeRedis:
    """只实现限流用到的 INCR / EXPIRE / TTL。"""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.counters: dict[str, int] = {}
        self.expires: list[tuple[str, int]] = []

    async def incr(self, key: str) -> int:
        if self.fail:
            raise RuntimeError("redis down")
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.expires.append((key, seconds))
        return True

    async def ttl(self, key: str) -> int:
        return 60


@pytest.fixture(autouse=True)
def clean_memory_limiter():
    from app.services.security.rate_limiter import rate_limiter

    rate_limiter.clear()
    yield
    rate_limiter.clear()


class TestUnifiedLimiter:
    def test_redis_backend_counts_and_expires_once(self, monkeypatch):
        redis = _FakeRedis()

        async def _get_redis():
            return redis

        monkeypatch.setattr("app.core.redis.get_redis", _get_redis)

        results = [
            asyncio.run(check_rate_limit("rl:test", limit=2, window_seconds=60))
            for _ in range(3)
        ]

        assert [allowed for allowed, _ in results] == [True, True, False]
        assert results[0][1]["backend"] == "redis"
        assert redis.counters["rl:test"] == 3
        assert len(redis.expires) == 1, "只有首次计数才设置过期时间"
        print("[PASS] Redis 后端：INCR 计数、首次设置 EXPIRE、超限拒绝")

    def test_redis_failure_degrades_to_memory(self, monkeypatch):
        redis = _FakeRedis(fail=True)

        async def _get_redis():
            return redis

        monkeypatch.setattr("app.core.redis.get_redis", _get_redis)

        allowed, info = asyncio.run(
            check_rate_limit("rl:fallback", limit=1, window_seconds=60)
        )
        assert allowed is True
        assert info["backend"] == "memory"
        assert info.get("degraded") is True
        print("[PASS] Redis 故障 → 自动降级为进程内限流（服务不中断）")

    def test_zero_limit_means_unlimited(self):
        allowed, info = asyncio.run(
            check_rate_limit("rl:none", limit=0, window_seconds=60)
        )
        assert allowed is True and info["backend"] == "disabled"


class TestClientIpResolution:
    def test_uses_rightmost_hop_for_single_trusted_proxy(self, monkeypatch):
        _patch_settings(monkeypatch, TRUSTED_PROXY_COUNT=1)
        request = _FakeRequest(
            headers={"X-Forwarded-For": "6.6.6.6, 9.9.9.9"}, client_host="127.0.0.1"
        )
        # 9.9.9.9 才是我们信任的代理追加的；6.6.6.6 可以是客户端伪造的
        assert client_ip(request) == "9.9.9.9"
        print("[PASS] X-Forwarded-For 取最右侧（不可伪造）而非最左侧")

    def test_supports_multiple_trusted_proxies(self, monkeypatch):
        _patch_settings(monkeypatch, TRUSTED_PROXY_COUNT=2)
        request = _FakeRequest(headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 3.3.3.3"})
        assert client_ip(request) == "2.2.2.2"

    def test_falls_back_to_socket_peer(self):
        assert client_ip(_FakeRequest(client_host="10.1.2.3")) == "10.1.2.3"



class TestStreamEndpointsAreLimited:
    def _override_user(self, monkeypatch):
        from app.auth.deps import get_current_user, get_optional_user
        from app.main import app

        class _User:
            id = 4242
            username = "limited"
            role = "USER"

        # 依赖"接线"两类端点都要覆盖，否则测试会因为 401 而不是 429 失败：
        # * /api/knowledge/query/stream → get_current_user（JWT 必填）
        # * /api/chat/*               → get_optional_user（JWT 可选 + API Key，审计 §6.1-3）
        monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: _User())
        monkeypatch.setitem(app.dependency_overrides, get_optional_user, lambda: _User())

    @staticmethod
    def _force_memory_limiter(monkeypatch):
        async def _get_redis():
            return None

        monkeypatch.setattr("app.core.redis.get_redis", _get_redis)

    def test_chat_stream_is_rate_limited(self, client, monkeypatch):
        import app.api.chat as chat_api

        self._override_user(monkeypatch)
        # 突发限额压到 1 次/窗口，并强制走进程内实现
        _patch_settings(monkeypatch, RATE_LIMIT_CHAT=1, RATE_LIMIT_WINDOW=60)
        self._force_memory_limiter(monkeypatch)

        async def fake_stream(*args, **kwargs):
            yield "你好"

        monkeypatch.setattr(chat_api.chat_service, "stream_chat", fake_stream)

        first = client.post("/api/chat/stream", json={"message": "hi"})
        second = client.post("/api/chat/stream", json={"message": "hi"})

        assert first.status_code == 200, first.text
        assert second.status_code == 429, second.text
        assert second.json()["code"] == "RATE_LIMITED"
        print("[PASS] /api/chat/stream 受路由级限流保护（此前可绕过）")

    def test_knowledge_stream_is_rate_limited(self, client, monkeypatch):
        from app.api import knowledge_query as kq_api

        self._override_user(monkeypatch)
        _patch_settings(monkeypatch, RATE_LIMIT_CHAT=1, RATE_LIMIT_WINDOW=60)
        self._force_memory_limiter(monkeypatch)

        async def fake_stream(*args, **kwargs):
            yield "答案"

        monkeypatch.setattr(kq_api.chat_service, "stream_query_knowledge", fake_stream)

        payload = {"question": "q", "knowledge_base_id": 1}
        first = client.post("/api/knowledge/query/stream", json=payload)
        second = client.post("/api/knowledge/query/stream", json=payload)

        assert first.status_code == 200, first.text
        assert second.status_code == 429, second.text
        print("[PASS] /api/knowledge/query/stream 受路由级限流保护（此前可绕过）")
