"""Phase 3 §5.6 可观测性的回归测试。

覆盖内容
--------
1. **`/metrics` 路由**：审计 §5.6 实测它**未注册**（404），Prometheus 抓取目标
   永远 down；这里断言已注册且能吐出指标。
2. **请求级指标与 request_id**：中间件给每个请求分配 / 透传 request_id，
   记录 ``knowledge_request_total``，并回写响应头。
3. **健康检查**：真实探测 DB / 向量库 / 嵌入 / Redis / LLM，依赖不可用必须体现
   在 ``status`` 与 ``checks`` 里（而不是硬编码 healthy）。
4. **Token 用量落库**（审计 §3.4）：``usage_service.record`` 此前零调用点，
   这里断言 ChatService 真的把 usage 写进 ``llm_usages``。
5. **指标辅助函数安全**：未安装 prometheus_client 时不得抛异常打断业务。
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.context import get_request_id, new_request_id, set_request_id  # noqa: E402
from app.services.llm.base import LLMUsageInfo, estimate_tokens  # noqa: E402
from app.services import metrics as metrics_module  # noqa: E402


# ---------------------------------------------------------------------------
# 1: /metrics 路由
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    def test_metrics_endpoint_is_registered(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200, "审计 §5.6：/metrics 曾 404"
        body = response.text
        assert "knowledge_request_total" in body
        for name in (
            "knowledge_rag_stage_latency_seconds",
            "knowledge_retry_total",
            "knowledge_abstention_total",
            "knowledge_document_status_total",
        ):
            assert name in body, f"缺少指标 {name}"
        print("[PASS] /metrics 已注册并包含 RAG/重试/拒答/文档指标")

    def test_track_helpers_never_raise(self):
        metrics_module.track_rag_stage("unit", 0.01)
        metrics_module.track_retrieval_chunks("unit", 3)
        metrics_module.track_abstention("no_context")
        metrics_module.track_retry("unit")
        metrics_module.track_retry_exhausted("unit")
        metrics_module.track_document_status("completed")
        metrics_module.track_document_dedup("created")
        print("[PASS] 指标辅助函数全部可安全调用")


# ---------------------------------------------------------------------------
# 2: request_id + 请求级指标
# ---------------------------------------------------------------------------


class TestRequestContextMiddleware:
    def test_response_carries_request_id_and_timing(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID"), "响应应带 request_id"
        assert response.headers.get("X-Response-Time-Ms"), "响应应带耗时"
        print(
            f"[PASS] 响应头携带 X-Request-ID={response.headers['X-Request-ID'][:8]}… / "
            f"X-Response-Time-Ms={response.headers['X-Response-Time-Ms']}"
        )

    def test_incoming_request_id_is_propagated(self, client):
        response = client.get("/openapi.json", headers={"X-Request-ID": "trace-abc-123"})
        assert response.headers["X-Request-ID"] == "trace-abc-123"
        print("[PASS] 上游传入的 X-Request-ID 被透传")

    def test_request_is_counted_in_metrics(self, client):
        client.get("/openapi.json")
        body = client.get("/metrics").text
        assert 'endpoint="/openapi.json"' in body
        print("[PASS] 请求被计入 knowledge_request_total（track_request 有调用点）")

    def test_contextvar_helpers(self):
        assert set_request_id("rid-1") == "rid-1"
        assert get_request_id() == "rid-1"
        assert set_request_id("") == "-", "空值退化为占位符"
        assert len(new_request_id()) == 16
        print("[PASS] request_id contextvar 读写正常")


# ---------------------------------------------------------------------------
# 3: 健康检查（真实探测）
# ---------------------------------------------------------------------------


class TestHealthProbe:
    def test_health_reports_each_dependency(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()

        assert body["status"] in {"healthy", "degraded", "unhealthy"}
        for name in ("database", "vector_store", "embedding", "redis", "llm"):
            assert name in body["checks"], f"缺少依赖探测 {name}"
            assert "ok" in body["checks"][name]

        # 兼容字段仍在（老前端 / 探针按布尔值判断）
        assert isinstance(body["embedding_model"], bool)
        assert isinstance(body["llm_configured"], bool)
        assert body["request_id"]
        # 测试环境：DB 可用，向量库/嵌入未初始化 → 必须体现为 degraded
        assert body["checks"]["database"]["ok"] is True
        assert body["status"] == "degraded", body["checks"]
        print(f"[PASS] /api/health 真实探测各依赖: status={body['status']}")

    def test_database_failure_makes_status_unhealthy(self, client, monkeypatch):
        import app.storage.database as storage_module

        def _broken_session():
            raise RuntimeError("database down")

        monkeypatch.setattr(storage_module, "async_session", _broken_session)

        body = client.get("/api/health").json()
        assert body["status"] == "unhealthy"
        assert body["checks"]["database"]["ok"] is False
        assert "database down" in body["checks"]["database"]["detail"]
        print("[PASS] DB 不可用 → status=unhealthy（探针不再是硬编码 healthy）")

    def test_probe_timeout_is_reported_not_raised(self, monkeypatch):
        import app.api.health as health_module

        async def _hang():
            await asyncio.sleep(5)

        monkeypatch.setattr(health_module, "PROBE_TIMEOUT", 0.01)
        name, result = asyncio.run(health_module._run_probe("slow", _hang()))
        assert name == "slow"
        assert result["ok"] is False
        assert "超时" in result["detail"]
        print("[PASS] 探测超时被转换成结果结构，而不是异常")


# ---------------------------------------------------------------------------
# 4: Token 用量落库（审计 §3.4）
# ---------------------------------------------------------------------------


class _PromptProvider:
    system_prompt = "你是助手。"


class _UsageProvider:
    """返回**真实 usage**（estimated=False）的假 provider。"""

    def __init__(
        self,
        answer: str = "答案",
        prompt_tokens: int = 11,
        completion_tokens: int = 7,
    ):
        self.answer = answer
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.calls = 0

    async def chat_with_usage(self, messages, stream: bool = False, **kwargs):
        self.calls += 1
        return self.answer, LLMUsageInfo(
            model="fake-model",
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            latency_ms=12.5,
            estimated=False,
        )

    async def chat(self, messages, stream: bool = False, **kwargs):
        self.calls += 1
        return self.answer


class _StreamProvider:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens

    async def chat(self, messages, stream: bool = False, **kwargs):
        async def _gen():
            for token in self.tokens:
                yield token

        return _gen()


def _service_with(provider):
    from app.services.chat_service import ChatService

    svc = object.__new__(ChatService)
    svc._llm = provider
    svc.prompt_provider = _PromptProvider()
    return svc


def _create_user(temp_db, user_id: int = 1):
    async def scenario():
        from app.models.user import User

        async with temp_db.session() as db:
            db.add(User(id=user_id, username=f"u{user_id}", password_hash="x"))
            await db.commit()

    asyncio.run(scenario())


def _llm_usages(temp_db):
    async def scenario():
        from sqlalchemy import select

        from app.models.llm_usage import LLMUsage

        async with temp_db.session() as db:
            result = await db.execute(select(LLMUsage))
            return list(result.scalars().all())

    return asyncio.run(scenario())


class TestTokenUsageRecording:
    def test_chat_records_real_usage(self, temp_db):
        _create_user(temp_db)
        svc = _service_with(_UsageProvider())

        async def scenario():
            async with temp_db.session() as db:
                return await svc.chat("你好", session=db, user_id=1)

        assert asyncio.run(scenario()) == "答案"

        rows = _llm_usages(temp_db)
        assert len(rows) == 1, "chat() 必须把 usage 写进 llm_usages（审计 §3.4 零调用点）"
        row = rows[0]
        assert (row.prompt_tokens, row.completion_tokens, row.total_tokens) == (11, 7, 18)
        assert row.model == "fake-model"
        assert row.user_id == 1
        print(f"[PASS] chat() 写入 llm_usages: total_tokens={row.total_tokens}")

    def test_without_session_metrics_only(self, temp_db):
        _create_user(temp_db)
        svc = _service_with(_UsageProvider())

        assert asyncio.run(svc.chat("你好")) == "答案"
        assert _llm_usages(temp_db) == [], "无会话时不应写库（也不应报错）"
        print("[PASS] 无 DB 会话时只上报指标、不落库")

    def test_streaming_records_estimated_usage(self, temp_db):
        _create_user(temp_db)
        svc = _service_with(_StreamProvider(["你", "好"]))

        async def scenario():
            async with temp_db.session() as db:
                return [c async for c in svc.stream_chat("你好", session=db, user_id=1)]

        assert asyncio.run(scenario()) == ["你", "好"]

        rows = _llm_usages(temp_db)
        assert len(rows) == 1, "流式也必须收尾写用量（否则主链路 token 统计仍为 0）"
        assert rows[0].prompt_tokens > 0
        assert rows[0].completion_tokens > 0
        print(
            f"[PASS] 流式收尾写入估算 usage: "
            f"prompt={rows[0].prompt_tokens}, completion={rows[0].completion_tokens}"
        )

    def test_estimate_tokens_heuristic(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("hello world") >= 1
        assert estimate_tokens("中" * 10) >= 10
        assert LLMUsageInfo(prompt_tokens=3, completion_tokens=4).total_tokens == 7
        print("[PASS] token 估算与总计计算正常")

