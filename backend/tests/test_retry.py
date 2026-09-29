"""Phase 3 §5.2 统一重试（``app.core.retry``）的回归测试。

覆盖内容
--------
1. **错误分类**：429 / 5xx / 超时 / 连接错误可重试；401 / 403 / 400 / 解析失败
   不可重试 —— 与评测裁判共用同一判定（``evaluation.judge.is_transient_error``）。
2. **退避**：指数增长 + 上限截断 + 抖动区间。
3. **``retry_async``**：重试后成功、不可重试立即抛出、耗尽抛 ``RetryExhausted``
   且保留根因、``RETRY_ENABLED=false`` 退化为单次调用、``on_retry`` 支持异步回调。
4. **``retry_stream``**：首字节前失败可重试；**已产出 token 后不重试**。
5. **线上接线**：LLM 调用（chat_service）、Embedding 调用（embedding_service）、
   文档级重试（DocumentProcessingTask + ``Document.retry_count``）。
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.retry import (  # noqa: E402
    RetryExhausted,
    RetryPolicy,
    backoff_delay,
    embedding_policy,
    is_retryable,
    llm_policy,
    retry_async,
    retry_stream,
    task_policy,
)


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch):
    """把退避压到 0 —— 测试不应该真的睡 1/2/4 秒。

    注意：本套件里有多个测试模块会 ``importlib.reload(app.core.config)``，
    每次 reload 都会产生**新的** ``settings`` 实例；因此这里必须按
    「当前模块属性」而不是「本文件导入时的引用」去打补丁，否则补丁打在
    旧对象上，``app.core.retry`` 读到的仍是默认值。
    """
    import app.core.config as config_module

    current = config_module.settings
    overrides = {
        "RETRY_ENABLED": True,
        "RETRY_MAX_ATTEMPTS": 3,
        "RETRY_BASE_DELAY": 0.0,
        "RETRY_MAX_DELAY": 0.0,
        "RETRY_JITTER": 0.0,
        "LLM_RETRY_MAX_ATTEMPTS": 3,
        "EMBEDDING_RETRY_MAX_ATTEMPTS": 3,
        "TASK_RETRY_MAX_ATTEMPTS": 3,
        "TASK_RETRY_BACKOFF_S": 0.0,
        "TASK_RETRY_MAX_BACKOFF_S": 0.0,
    }
    for name, value in overrides.items():
        monkeypatch.setattr(current, name, value)


class _Recorder:
    """记录 sleep 调用（不真的等待）。"""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


# ---------------------------------------------------------------------------
# 1: 错误分类
# ---------------------------------------------------------------------------


class TestErrorClassification:
    def test_transient_errors_are_retryable(self):
        cases = [
            RuntimeError("Error code: 429 - rate limit exceeded"),
            RuntimeError("You've reached the API rate limit for free users"),
            RuntimeError("504 Gateway Timeout"),
            RuntimeError("503 Service Unavailable"),
            RuntimeError("APIConnectionError: Connection error."),
            RuntimeError("APITimeoutError: Request timed out"),
            RuntimeError("ReadTimeout: read timeout"),
            asyncio.TimeoutError("operation timed out"),
            ConnectionResetError("Connection reset by peer"),
        ]
        for exc in cases:
            assert is_retryable(exc), f"应可重试: {type(exc).__name__}: {exc}"
        print(f"[PASS] {len(cases)} 类瞬时错误判定为可重试")

    def test_client_errors_are_not_retryable(self):
        cases = [
            RuntimeError("401 Unauthorized: invalid api key"),
            RuntimeError("403 Forbidden"),
            RuntimeError("400 Bad Request: invalid parameter"),
            RuntimeError("422 Unprocessable Entity"),
            ValueError("bad request body"),
            TypeError("messages must be a list"),
            FileNotFoundError("missing.pdf"),
        ]
        for exc in cases:
            assert not is_retryable(exc), f"不应重试: {type(exc).__name__}: {exc}"
        print(f"[PASS] {len(cases)} 类客户端/输入错误判定为不可重试")

    def test_401_wins_over_429_mention(self):
        """同一条报文里既出现 401 又出现 429 时，以「不会成功」为准。"""
        assert not is_retryable(RuntimeError("401 Unauthorized (note: 429 rate limit)"))

    def test_cancelled_error_is_never_retryable(self):
        assert not is_retryable(asyncio.CancelledError())

    def test_evaluation_judge_shares_the_same_classification(self):
        """评测裁判必须与线上共用一套判定（Phase 3 §5.2）。"""
        from evaluation.judge import is_transient_error

        assert is_transient_error(RuntimeError("Error code: 429 - rate limit exceeded"))
        assert is_transient_error(RuntimeError("APIConnectionError: Connection error."))
        assert not is_transient_error(RuntimeError("401 Unauthorized: invalid api key"))
        assert not is_transient_error(ValueError("bad request body"))
        print("[PASS] evaluation.judge.is_transient_error 委托给 app.core.retry")


# ---------------------------------------------------------------------------
# 2: 退避
# ---------------------------------------------------------------------------


class TestBackoff:
    def test_exponential_growth_without_jitter(self):
        policy = RetryPolicy(attempts=5, base_delay=1.0, max_delay=30.0, jitter=0.0)
        delays = [backoff_delay(a, policy) for a in range(1, 5)]
        assert delays == [1.0, 2.0, 4.0, 8.0]
        print(f"[PASS] 指数退避 {delays}")

    def test_capped_by_max_delay(self):
        policy = RetryPolicy(attempts=6, base_delay=1.0, max_delay=5.0, jitter=0.0)
        delays = [backoff_delay(a, policy) for a in range(1, 7)]
        assert delays == [1.0, 2.0, 4.0, 5.0, 5.0, 5.0]
        print(f"[PASS] 退避上限截断 {delays}")

    def test_jitter_stays_within_band(self):
        policy = RetryPolicy(attempts=3, base_delay=10.0, max_delay=100.0, jitter=0.2)
        for _ in range(50):
            assert 8.0 <= backoff_delay(1, policy) <= 12.0

    def test_disabled_policy_uses_single_attempt(self):
        assert RetryPolicy(enabled=False, attempts=5).effective_attempts() == 1

    def test_policies_read_settings(self):
        assert llm_policy().attempts == 3
        assert embedding_policy().attempts == 3
        assert task_policy().attempts == 3
        # 调用点可以覆盖次数（如 Query Rewrite 只要一次重试）
        assert llm_policy(attempts=2).attempts == 2


# ---------------------------------------------------------------------------
# 3: retry_async
# ---------------------------------------------------------------------------


class TestRetryAsync:
    def test_succeeds_after_transient_failures(self):
        recorder = _Recorder()
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("429 Too Many Requests")
            return "ok"

        result = asyncio.run(
            retry_async(
                flaky,
                policy=RetryPolicy(attempts=3),
                sleep=recorder,
                operation="flaky",
            )
        )
        assert result == "ok"
        assert calls["n"] == 3
        assert len(recorder.delays) == 2
        print(f"[PASS] 第 3 次调用成功（重试 {len(recorder.delays)} 次）")

    def test_non_retryable_error_is_raised_immediately(self):
        recorder = _Recorder()
        calls = {"n": 0}

        async def bad():
            calls["n"] += 1
            raise ValueError("文档内容为空，无法处理")

        with pytest.raises(ValueError):
            asyncio.run(retry_async(bad, policy=RetryPolicy(attempts=3), sleep=recorder))
        assert calls["n"] == 1, "不可重试错误只允许调用一次"
        assert recorder.delays == []
        print("[PASS] 不可重试错误立即抛出，无无效重试")

    def test_exhausted_retries_raise_retry_exhausted_with_root_cause(self):
        recorder = _Recorder()
        calls = {"n": 0}

        async def always_429():
            calls["n"] += 1
            raise RuntimeError("429 rate limit exceeded")

        with pytest.raises(RetryExhausted) as excinfo:
            asyncio.run(
                retry_async(
                    always_429,
                    policy=RetryPolicy(attempts=3),
                    sleep=recorder,
                    operation="embed_documents",
                )
            )

        exc = excinfo.value
        assert calls["n"] == 3
        assert exc.attempts == 3
        assert isinstance(exc.last_error, RuntimeError)
        assert "429" in str(exc)
        # 根因仍可重试 → 允许上层（文档级）再试一次
        assert is_retryable(exc)
        assert not is_retryable(RetryExhausted(2, ValueError("bad request")))
        print(f"[PASS] 耗尽重试抛 RetryExhausted: {exc}")

    def test_single_attempt_when_retry_disabled(self):
        recorder = _Recorder()
        calls = {"n": 0}

        async def always_429():
            calls["n"] += 1
            raise RuntimeError("429")

        with pytest.raises(RuntimeError):
            asyncio.run(
                retry_async(
                    always_429,
                    policy=RetryPolicy(attempts=3, enabled=False),
                    sleep=recorder,
                )
            )
        assert calls["n"] == 1
        assert recorder.delays == []
        print("[PASS] RETRY_ENABLED=false 时退化为单次调用")

    def test_on_retry_callback_can_be_async(self):
        seen: list[int] = []
        recorder = _Recorder()
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("503 Service Unavailable")
            return 1

        async def on_retry(attempt, exc, delay):
            seen.append(attempt)

        asyncio.run(
            retry_async(
                flaky,
                policy=RetryPolicy(attempts=2, base_delay=0.0),
                sleep=recorder,
                on_retry=on_retry,
            )
        )
        assert seen == [1]
        print("[PASS] on_retry 支持协程回调（文档级重试用它写 retry_count）")


# ---------------------------------------------------------------------------
# 4: retry_stream（流式：只重试首字节之前）
# ---------------------------------------------------------------------------


def _stream_of(tokens: list[str]):
    async def _gen():
        for token in tokens:
            yield token

    return _gen()


class _FlakyStreamProvider:
    """前 ``fail_times`` 次调用直接抛 429；之后返回正常流。"""

    def __init__(self, tokens: list[str] | None = None, fail_times: int = 1):
        self.calls = 0
        self.fail_times = fail_times
        self.tokens = tokens or ["你", "好"]

    async def chat(self, messages, stream: bool = False, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("429 Too Many Requests")
        return _stream_of(self.tokens)


class _MidStreamFailProvider:
    """先吐一个 token 再抛错（重试会导致重复渲染，因此不允许重试）。"""

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, stream: bool = False, **kwargs):
        self.calls += 1

        async def _gen():
            yield "部分"
            raise RuntimeError("429 Too Many Requests")

        return _gen()


class TestRetryStream:
    def test_retries_before_first_token(self):
        recorder = _Recorder()
        provider = _FlakyStreamProvider()

        async def collect():
            return [
                chunk
                async for chunk in retry_stream(
                    lambda: provider.chat([], stream=True),
                    policy=RetryPolicy(attempts=3),
                    sleep=recorder,
                )
            ]

        chunks = asyncio.run(collect())
        assert chunks == ["你", "好"]
        assert provider.calls == 2
        print("[PASS] 首字节前失败 → 重试成功")

    def test_does_not_retry_after_tokens_emitted(self):
        recorder = _Recorder()
        provider = _MidStreamFailProvider()

        async def collect():
            return [
                chunk
                async for chunk in retry_stream(
                    lambda: provider.chat([], stream=True),
                    policy=RetryPolicy(attempts=3),
                    sleep=recorder,
                )
            ]

        with pytest.raises(RuntimeError):
            asyncio.run(collect())
        assert provider.calls == 1, "已产出 token 后不得重试（否则前端重复追加）"
        print("[PASS] 已产出 token 后失败不重试")

    def test_non_retryable_stream_error_propagates(self):
        recorder = _Recorder()
        calls = {"n": 0}

        async def bad():
            calls["n"] += 1
            raise RuntimeError("401 Unauthorized")

        async def collect():
            return [
                chunk
                async for chunk in retry_stream(
                    bad, policy=RetryPolicy(attempts=3), sleep=recorder
                )
            ]

        with pytest.raises(RuntimeError):
            asyncio.run(collect())
        assert calls["n"] == 1

    def test_plain_string_stream_is_yielded_once(self):
        async def make_stream():
            return "整段回答"

        async def collect():
            return [
                c async for c in retry_stream(make_stream, policy=RetryPolicy(attempts=1))
            ]

        assert asyncio.run(collect()) == ["整段回答"]


# ---------------------------------------------------------------------------
# 5: 线上接线（LLM / Embedding）
# ---------------------------------------------------------------------------


class _StaticPromptProvider:
    """最小 prompt provider（只满足 chat/stream_chat 的读取）。"""

    system_prompt = "你是助手。"


class _FlakyTextProvider:
    """前 ``fail_times`` 次非流式调用失败（429），之后返回固定文本。"""

    def __init__(self, answer: str = "最终回答", fail_times: int = 1):
        self.answer = answer
        self.fail_times = fail_times
        self.calls = 0

    async def chat(self, messages, stream: bool = False, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("429 Too Many Requests")
        return self.answer


def _chat_service_with(provider):
    """构造不加载检索/模型的 ChatService（只测 LLM 调用接线）。"""
    from app.services.chat_service import ChatService

    svc = object.__new__(ChatService)
    svc._llm = provider
    svc.prompt_provider = _StaticPromptProvider()
    return svc


class TestLLMRetryWiring:
    def test_non_stream_chat_retries_transient_failure(self):
        provider = _FlakyTextProvider()
        svc = _chat_service_with(provider)

        answer = asyncio.run(svc.chat("你好"))
        assert answer == "最终回答"
        assert provider.calls == 2, "一次 429 不应直接把错误抛给用户"
        print(f"[PASS] chat() 重试成功（调用 {provider.calls} 次）")

    def test_auth_error_is_not_retried_and_not_leaked(self):
        provider = _FlakyTextProvider()

        async def _auth_failure(messages, stream: bool = False, **kwargs):
            provider.calls += 1
            raise RuntimeError("401 Unauthorized: invalid api key")

        provider.chat = _auth_failure  # type: ignore[assignment]
        svc = _chat_service_with(provider)

        answer = asyncio.run(svc.chat("你好"))
        assert "抱歉" in answer, "鉴权失败对用户仍应是友好文案"
        assert provider.calls == 1, "401 重试再多次也不会成功"
        print("[PASS] 401 不重试，且不把内部报文当回答返回")

    def test_stream_chat_retries_before_first_token(self):
        provider = _FlakyStreamProvider(tokens=["你", "好"])
        svc = _chat_service_with(provider)

        async def collect():
            return [chunk async for chunk in svc.stream_chat("你好")]

        chunks = asyncio.run(collect())
        assert chunks == ["你", "好"]
        assert provider.calls == 2
        print("[PASS] stream_chat() 首字节前失败可重试")

    def test_stream_chat_mid_stream_failure_is_not_retried(self):
        provider = _MidStreamFailProvider()
        svc = _chat_service_with(provider)

        async def collect():
            return [chunk async for chunk in svc.stream_chat("你好")]

        chunks = asyncio.run(collect())
        assert provider.calls == 1
        assert any("抱歉" in c for c in chunks), chunks
        print("[PASS] 流式中途失败不重试，且以友好文案收尾")


class _FlakyEmbeddingProvider:
    """前 ``fail_times`` 次调用失败（429），之后返回固定向量。"""

    def __init__(self, fail_times: int = 1):
        self.fail_times = fail_times
        self.calls = 0

    async def _maybe_fail(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("429 Too Many Requests")

    async def embed_query(self, text: str):
        await self._maybe_fail()
        return [0.1, 0.2]

    async def embed_documents(self, texts: list[str]):
        await self._maybe_fail()
        return [[0.1, 0.2] for _ in texts]


class TestEmbeddingRetryWiring:
    def _service(self, provider):
        from app.services.embedding_service import EmbeddingService

        svc = object.__new__(EmbeddingService)
        svc._provider = provider
        return svc

    def test_embed_query_retries(self):
        provider = _FlakyEmbeddingProvider()
        svc = self._service(provider)

        vector = asyncio.run(svc.embed_query("问题"))
        assert vector == [0.1, 0.2]
        assert provider.calls == 2
        print("[PASS] embed_query() 重试成功")

    def test_embed_texts_exhausted_raises_retry_exhausted(self):
        provider = _FlakyEmbeddingProvider(fail_times=99)
        svc = self._service(provider)

        with pytest.raises(RetryExhausted) as excinfo:
            asyncio.run(svc.embed_texts(["a", "b"]))
        assert excinfo.value.attempts == 3
        assert provider.calls == 3
        print("[PASS] 嵌入调用耗尽重试抛 RetryExhausted（保留 429 根因）")


# ---------------------------------------------------------------------------
# 6: 文档级重试（DocumentProcessingTask + Document.retry_count）
# ---------------------------------------------------------------------------


def _add_document(temp_db, document_id: str):
    from app.models.document import Document, DocumentStatus

    async def scenario():
        async with temp_db.session() as db:
            db.add(
                Document(
                    id=document_id,
                    filename="a.txt",
                    file_size=1,
                    file_type=".txt",
                    status=DocumentStatus.PENDING.value,
                    knowledge_base_id=1,
                )
            )
            await db.commit()

    asyncio.run(scenario())


def _read_document(temp_db, document_id: str):
    from sqlalchemy import select

    from app.models.document import Document

    async def scenario():
        async with temp_db.session() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            return result.scalar_one()

    return asyncio.run(scenario())


def _patch_db(monkeypatch, temp_db):
    """让任务内部使用的 ``async_session`` 指向临时库。"""
    import app.storage.database as storage_module

    monkeypatch.setattr(storage_module, "async_session", temp_db.session)


class TestDocumentLevelRetry:
    """文档级重试：只重试瞬时错误，并把次数写进 ``retry_count``。"""

    def _run_task(self, monkeypatch, temp_db, pipeline_factory, document_id: str):
        from app.services.tasks import DocumentProcessingTask

        monkeypatch.setattr(
            "app.services.knowledge.pipeline.KnowledgePipeline", pipeline_factory
        )
        _patch_db(monkeypatch, temp_db)
        _add_document(temp_db, document_id)

        task = DocumentProcessingTask(
            document_id=document_id,
            file_path="/tmp/a.txt",
            filename="a.txt",
            knowledge_base_id=1,
        )
        return task, asyncio.run(task.run())

    def test_transient_failure_is_retried_then_completed(self, temp_db, monkeypatch):
        calls = {"n": 0}

        class _FlakyPipeline:
            async def process_document(self, context):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise RuntimeError("429 Too Many Requests")
                return 5

        _, result = self._run_task(
            monkeypatch, temp_db, lambda: _FlakyPipeline(), "doc-retry-ok"
        )

        doc = _read_document(temp_db, "doc-retry-ok")
        assert calls["n"] == 3
        assert doc.status == "completed"
        assert doc.chunk_count == 5
        assert doc.retry_count == 2
        assert result["retry_count"] == 2
        print(f"[PASS] 429 触发文档级重试并成功（retry_count={doc.retry_count}）")

    def test_non_retryable_failure_fails_without_retry(self, temp_db, monkeypatch):
        calls = {"n": 0}

        class _EmptyDocPipeline:
            async def process_document(self, context):
                calls["n"] += 1
                raise ValueError("文档内容为空，无法处理")

        self._run_task_and_expect_failure(
            monkeypatch, temp_db, lambda: _EmptyDocPipeline(), "doc-empty"
        )

        doc = _read_document(temp_db, "doc-empty")
        assert calls["n"] == 1, "不可重试错误不应触发文档级重试"
        assert doc.status == "failed"
        assert doc.retry_count == 0
        assert "文档内容为空" in (doc.error_message or "")
        print("[PASS] 不可重试错误不重试，直接 FAILED")

    def test_exhausted_retries_mark_failed_with_attempt_count(self, temp_db, monkeypatch):
        calls = {"n": 0}

        class _Always429Pipeline:
            async def process_document(self, context):
                calls["n"] += 1
                raise RuntimeError("429 Too Many Requests")

        self._run_task_and_expect_failure(
            monkeypatch, temp_db, lambda: _Always429Pipeline(), "doc-exhausted"
        )

        doc = _read_document(temp_db, "doc-exhausted")
        assert calls["n"] == 3, "TASK_RETRY_MAX_ATTEMPTS=3 → 共 3 次尝试"
        assert doc.status == "failed"
        assert doc.retry_count == 2
        assert "429" in (doc.error_message or "")
        print(f"[PASS] 重试耗尽 → FAILED（尝试 {calls['n']} 次，retry_count=2）")

    def _run_task_and_expect_failure(
        self, monkeypatch, temp_db, pipeline_factory, document_id: str
    ):
        """跑任务并断言它最终失败（Worker 会把异常记为任务失败）。"""
        with pytest.raises(Exception):
            self._run_task(monkeypatch, temp_db, pipeline_factory, document_id)
