"""
Redis 客户端测试（P0-1）

背景：``core/redis.py`` 曾传入 ``protocol=1``，而 redis-py 只接受
RESP2(2) / RESP3(3)，``Connection(protocol=1)`` 会直接抛
``ConnectionError: protocol must be either 2 or 3``
→ ``get_redis()`` 恒返回 None → 基于 Redis 的限流 fail-open（等同不存在）。

测试:
1. 协议版本配置正确（回归守卫）
2. 非法协议确实会被 redis-py 拒绝（根因固定）
3. Redis 不可达时优雅降级为 None
4. 失败后进入冷却期，不再每个请求重试建连
5. 成功路径：连接可用、单例复用
6. close/reset 状态清理
7. bootstrap_infrastructure 启动自检（Cache/Worker 真实生效）
8. _get_cache_backend 优先读 .env（settings），而非仅读 os.environ
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.core import redis as redis_module  # noqa: E402
from app.services import factory as factory_module  # noqa: E402

UNREACHABLE_URL = "redis://127.0.0.1:1/0"


class _FakeRedis:
    """最小 Redis 客户端替身。"""

    def __init__(self, ping_error: Exception | None = None):
        self.ping_calls = 0
        self.closed = False
        self._ping_error = ping_error

    async def ping(self):
        self.ping_calls += 1
        if self._ping_error is not None:
            raise self._ping_error
        return True

    async def close(self):
        self.closed = True


def _reset(monkeypatch):
    """重置 redis 模块状态与超时（保证测试之间互不影响）。"""
    monkeypatch.setattr(redis_module, "REDIS_SOCKET_TIMEOUT", 0.5)
    redis_module.reset_redis_state()


# ---------------------------------------------------------------------------
# 1-3: 协议配置
# ---------------------------------------------------------------------------


class TestRedisProtocol:
    def test_protocol_is_resp2(self):
        """回归守卫：protocol 必须是 redis-py 接受的 2 或 3。"""
        kwargs = redis_module.build_client_kwargs()
        assert redis_module.REDIS_PROTOCOL in (2, 3), (
            f"非法 RESP 协议: {redis_module.REDIS_PROTOCOL}"
        )
        assert kwargs["protocol"] == 2, "应使用 RESP2 以兼容旧版 Redis"
        print(f"[PASS] protocol={kwargs['protocol']} (RESP2)")

    def test_protocol_1_is_rejected_by_redis_py(self):
        """根因固定：protocol=1 会被 redis-py 直接拒绝。"""
        import redis.asyncio as aioredis

        try:
            aioredis.Connection(protocol=1)
            raise AssertionError("protocol=1 本应被拒绝")
        except AssertionError:
            raise
        except Exception as exc:
            assert "protocol" in str(exc).lower(), f"意外异常: {exc}"
            print(f"[PASS] protocol=1 被拒绝: {type(exc).__name__}: {exc}")

    def test_client_kwargs_build_valid_connection(self):
        """build_client_kwargs() 的参数必须能构造出合法 Connection。"""
        import redis.asyncio as aioredis

        conn = aioredis.Connection(**redis_module.build_client_kwargs())
        assert conn is not None
        print("[PASS] Connection 构造成功（参数合法）")


# ---------------------------------------------------------------------------
# 3-6: get_redis 优雅降级
# ---------------------------------------------------------------------------


class TestGetRedis:
    def test_unreachable_returns_none(self, monkeypatch):
        """Redis 不可达时必须返回 None（不抛异常），保证服务可用。"""
        _reset(monkeypatch)
        monkeypatch.setattr(redis_module.settings, "REDIS_URL", UNREACHABLE_URL)

        assert asyncio.run(redis_module.get_redis()) is None
        print("[PASS] Redis 不可达 → 返回 None（优雅降级）")

    def test_failure_enters_cooldown(self, monkeypatch):
        """失败后进入冷却期：第二次调用不再尝试建连。"""
        _reset(monkeypatch)
        monkeypatch.setattr(redis_module.settings, "REDIS_URL", UNREACHABLE_URL)

        calls = []
        real_from_url = redis_module.aioredis.from_url

        def counting_from_url(*args, **kwargs):
            calls.append(kwargs)
            return real_from_url(*args, **kwargs)

        monkeypatch.setattr(redis_module.aioredis, "from_url", counting_from_url)

        async def run():
            return await redis_module.get_redis(), await redis_module.get_redis()

        first, second = asyncio.run(run())
        assert first is None and second is None
        assert len(calls) == 1, f"冷却期内不应重复建连，实际 {len(calls)} 次"
        print("[PASS] 失败后进入冷却期，未重复建连")

    def test_success_is_cached(self, monkeypatch):
        """连接成功时复用单例，并清空冷却状态。"""
        _reset(monkeypatch)
        fake = _FakeRedis()
        created = []

        def fake_from_url(*args, **kwargs):
            created.append(kwargs)
            return fake

        monkeypatch.setattr(redis_module.aioredis, "from_url", fake_from_url)
        monkeypatch.setattr(redis_module, "REDIS_AVAILABLE", True)

        async def run():
            return await redis_module.get_redis(), await redis_module.get_redis()

        first, second = asyncio.run(run())
        assert first is fake and second is fake
        assert fake.ping_calls == 1, "只应在首次建连时 ping"
        assert len(created) == 1, "应复用单例，不应重复建连"
        assert created[0]["protocol"] == 2, "建连参数中的协议必须是 RESP2"
        print("[PASS] 成功路径单例复用 + 协议参数正确")

    def test_close_resets_state(self, monkeypatch):
        """close_redis 应关闭连接并清空单例/冷却。"""
        _reset(monkeypatch)
        fake = _FakeRedis()
        monkeypatch.setattr(redis_module.aioredis, "from_url", lambda *a, **k: fake)
        monkeypatch.setattr(redis_module, "REDIS_AVAILABLE", True)

        async def run():
            await redis_module.get_redis()
            await redis_module.close_redis()
            return await redis_module.get_redis()

        reopened = asyncio.run(run())
        assert fake.closed is True, "close() 应被调用"
        assert reopened is fake, "关闭后应可重新建立连接"
        print("[PASS] close_redis 清理状态成功")


# ---------------------------------------------------------------------------
# 7-8: 启动自检 / 配置来源
# ---------------------------------------------------------------------------


class TestBootstrapInfrastructure:
    def test_memory_backend(self, monkeypatch):
        """CACHE_BACKEND=memory → MemoryCache + LocalWorker。"""
        _reset(monkeypatch)
        monkeypatch.setenv("CACHE_BACKEND", "memory")
        monkeypatch.setenv("WORKER_BACKEND", "local")

        status = asyncio.run(factory_module.bootstrap_infrastructure())
        assert status.cache_type == "MemoryCache"
        assert status.worker_type == "LocalWorker"
        assert status.cache_backend == "memory"
        print(f"[PASS] bootstrap: {status.cache_type} / {status.worker_type}")

    def test_redis_backend_reports_unreachable(self, monkeypatch):
        """CACHE_BACKEND=redis 但 Redis 不可达 → 状态必须是可见的降级。"""
        _reset(monkeypatch)
        monkeypatch.setenv("CACHE_BACKEND", "redis")
        monkeypatch.setattr(redis_module.settings, "REDIS_URL", UNREACHABLE_URL)

        status = asyncio.run(factory_module.bootstrap_infrastructure())
        assert status.cache_type == "RedisCache", "必须真正创建 RedisCache"
        assert status.redis_reachable is False
        assert "fail-open" in status.details
        print(f"[PASS] bootstrap 降级可见: {status.details[:40]}…")

    def test_invalid_backend_fails_fast(self, monkeypatch):
        """非法 CACHE_BACKEND 必须显式失败，而不是静默用默认值。"""
        _reset(monkeypatch)
        monkeypatch.setenv("CACHE_BACKEND", "not-a-backend")

        try:
            asyncio.run(factory_module.bootstrap_infrastructure())
            raise AssertionError("非法 CACHE_BACKEND 应抛出 ValueError")
        except AssertionError:
            raise
        except ValueError as exc:
            assert "CACHE_BACKEND" in str(exc)
            print(f"[PASS] 非法 backend 显式失败: {exc}")

    def test_settings_used_when_env_absent(self, monkeypatch):
        """.env（settings）中的 CACHE_BACKEND 必须生效（回归：原先只读 os.getenv）。"""
        monkeypatch.delenv("CACHE_BACKEND", raising=False)
        monkeypatch.setattr(factory_module.settings, "CACHE_BACKEND", "redis")
        assert factory_module._get_cache_backend() == "redis"
        print("[PASS] settings.CACHE_BACKEND 生效")

    def test_env_overrides_settings(self, monkeypatch):
        """环境变量优先于 settings（便于测试与运行时覆盖）。"""
        monkeypatch.setenv("CACHE_BACKEND", "memory")
        monkeypatch.setattr(factory_module.settings, "CACHE_BACKEND", "redis")
        assert factory_module._get_cache_backend() == "memory"
        print("[PASS] 环境变量优先级正确")


if __name__ == "__main__":
    print("=" * 50)
    print("Redis 客户端测试 (P0-1) — 请使用 pytest 运行")
    print("=" * 50)

