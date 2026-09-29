"""统一重试策略（Phase 3 §5.2 Retry）。

为什么需要它
------------
审计 §5.2 记录：LLM / 嵌入调用失败时全链路**零重试** —— 一次 429、一次连接抖动
就会让整篇文档直接 FAILED，或让一次问答直接返回错误。Phase 2 的评测里 71 题中有
20 题因为裁判调用 429 丢掉判分，根因完全相同。

设计约束
--------
1. **只有一套实现**：评测侧（``evaluation/judge.py``）与线上侧共用
   :func:`is_retryable`，避免出现"评测重试、线上不重试"的双标准。
2. **只重试可能成功的错误**：网络 / 超时 / 429 / 5xx 等瞬时错误可重试；
   401 / 403 / 400 / 解析失败等**不会**因为重试而成功，直接抛出，
   避免把额度与时间浪费在必然失败的调用上。
3. **只包幂等调用**：本模块只用于只读、可重复执行的调用（embedding、LLM 生成、
   Query 改写）。带副作用的写操作（向量库写入、文件落盘）不在重试范围内。
4. **全部可配**：``RETRY_ENABLED`` / ``RETRY_MAX_ATTEMPTS`` / ``RETRY_BASE_DELAY``
   / ``RETRY_MAX_DELAY`` / ``RETRY_BACKOFF_FACTOR`` / ``RETRY_JITTER``，
   以及按调用类型覆盖的 ``LLM_RETRY_MAX_ATTEMPTS`` /
   ``EMBEDDING_RETRY_MAX_ATTEMPTS`` / ``TASK_RETRY_MAX_ATTEMPTS``。
   ``RETRY_ENABLED=false`` 可一键退化为单次调用。

用法::

    from ..core.retry import embedding_policy, retry_async

    embeddings = await retry_async(
        lambda: provider.embed_documents(chunks),
        policy=embedding_policy(),
        operation="embed_documents",
    )
"""
from __future__ import annotations

import asyncio
import inspect
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, TypeVar

from loguru import logger

T = TypeVar("T")

# ---------------------------------------------------------------------------
# 错误分类
# ---------------------------------------------------------------------------

#: 命中即判定为**不可重试**（重试也不会成功，只会浪费额度/时间）。
#: 顺序优先于 :data:`RETRYABLE_MARKERS`：``401`` 与 ``429`` 同时出现时以 401 为准。
NON_RETRYABLE_MARKERS: tuple[str, ...] = (
    "401",
    "403",
    "404",
    "422",
    "unauthorized",
    "forbidden",
    "invalid api key",
    "invalid_api_key",
    "invalid api-key",
    "bad request",
    "badrequesterror",
    "authenticationerror",
    "permissiondeniederror",
    "notfounderror",
    "unprocessableentityerror",
    "context_length_exceeded",
    "content policy",
    "model not found",
)

#: 命中即判定为**可重试**（网络抖动 / 限流 / 服务端 5xx / 超时）。
RETRYABLE_MARKERS: tuple[str, ...] = (
    "429",
    "rate limit",
    "too many requests",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "timeoutexception",
    "connecterror",
    "connectionerror",
    "connection error",
    "connection reset",
    "connection aborted",
    "remoteprotocolerror",
    "readerror",
    "read timeout",
    "ratelimiterror",
    "apiconnectionerror",
    "apitimeouterror",
    "internalservererror",
    "serviceunavailableerror",
    "overloadederror",
    "temporarily unavailable",
    "server error",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "overloaded",
)

#: 明确不可重试的异常类型（业务/输入错误，重试无意义）。
NON_RETRYABLE_TYPES: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    FileNotFoundError,
    PermissionError,
    NotImplementedError,
)



class RetryExhausted(RuntimeError):
    """重试次数耗尽后抛出的包装异常。

    保留原始异常（:attr:`last_error`）与尝试次数（:attr:`attempts`），
    让上层（如 ``Document.error_message``）既能记录"重试过几次"，
    又能通过 :func:`is_retryable` 判断根因是否仍然是瞬时错误。
    """

    def __init__(
        self,
        attempts: int,
        last_error: BaseException,
        operation: str = "",
    ) -> None:
        self.attempts = attempts
        self.last_error = last_error
        self.operation = operation
        super().__init__(
            f"{operation or '调用'} 在 {attempts} 次尝试后仍然失败: "
            f"{type(last_error).__name__}: {last_error}"
        )


def is_retryable(exc: BaseException) -> bool:
    """Return ``True`` when retrying the very same call may succeed.

    这是**全项目唯一**的重试判定入口：评测裁判与线上链路共用，
    避免两侧对"什么算瞬时错误"给出不同答案。
    """
    if isinstance(exc, asyncio.CancelledError):
        return False

    if isinstance(exc, RetryExhausted):
        # 内层已按策略重试过：只有根因仍可重试时，外层（文档级）才再试一次
        return exc.last_error is not None and is_retryable(exc.last_error)

    if isinstance(exc, NON_RETRYABLE_TYPES):
        return False

    text = f"{type(exc).__name__}: {exc}".lower()

    if any(marker in text for marker in NON_RETRYABLE_MARKERS):
        return False

    return any(marker in text for marker in RETRYABLE_MARKERS)


# ---------------------------------------------------------------------------
# 策略
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """重试策略：次数 + 指数退避 + 抖动。

    Attributes:
        attempts: **总**尝试次数（``1`` 表示不重试）。
        base_delay: 第一次重试前的等待秒数。
        max_delay: 单次等待上限（秒）。
        backoff_factor: 退避倍数（``2.0`` → 1s, 2s, 4s, ...）。
        jitter: 抖动比例（``0.2`` → ±20%），避免多任务同时重试造成二次限流。
        enabled: ``False`` 等价于 ``attempts=1``。
    """

    attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    jitter: float = 0.2
    enabled: bool = True

    def effective_attempts(self) -> int:
        """实际尝试次数（受 ``enabled`` 约束，至少 1 次）。"""
        if not self.enabled:
            return 1
        return max(1, int(self.attempts))


def _settings() -> Any:
    """延迟读取 settings，避免导入期循环依赖。"""
    from .config import settings

    return settings


def _policy(**overrides: Any) -> RetryPolicy:
    """从 settings 构造策略，``overrides`` 优先（仅覆盖非 None 值）。"""
    s = _settings()
    values: dict[str, Any] = {
        "attempts": int(getattr(s, "RETRY_MAX_ATTEMPTS", 3)),
        "base_delay": float(getattr(s, "RETRY_BASE_DELAY", 1.0)),
        "max_delay": float(getattr(s, "RETRY_MAX_DELAY", 30.0)),
        "backoff_factor": float(getattr(s, "RETRY_BACKOFF_FACTOR", 2.0)),
        "jitter": float(getattr(s, "RETRY_JITTER", 0.2)),
        "enabled": bool(getattr(s, "RETRY_ENABLED", True)),
    }
    for key, value in overrides.items():
        if value is not None:
            values[key] = value
    return RetryPolicy(**values)


def default_policy(**overrides: Any) -> RetryPolicy:
    """通用策略（读 ``RETRY_*``）。"""
    return _policy(**overrides)


def llm_policy(**overrides: Any) -> RetryPolicy:
    """LLM 生成策略（尝试次数可用 ``LLM_RETRY_MAX_ATTEMPTS`` 单独覆盖）。"""
    s = _settings()
    overrides.setdefault(
        "attempts", int(getattr(s, "LLM_RETRY_MAX_ATTEMPTS", 0)) or None
    )
    return _policy(**overrides)


def embedding_policy(**overrides: Any) -> RetryPolicy:
    """Embedding 策略（尝试次数可用 ``EMBEDDING_RETRY_MAX_ATTEMPTS`` 单独覆盖）。"""
    s = _settings()
    overrides.setdefault(
        "attempts", int(getattr(s, "EMBEDDING_RETRY_MAX_ATTEMPTS", 0)) or None
    )
    return _policy(**overrides)


def task_policy(**overrides: Any) -> RetryPolicy:
    """文档级（整篇入库）策略：次数少、退避长。

    文档处理内部已经对 embedding / LLM 做了调用级重试，这里再放大重试会成倍
    放大延迟与额度消耗，所以默认只额外重试一次、且退避更长。
    """
    s = _settings()
    overrides.setdefault("attempts", int(getattr(s, "TASK_RETRY_MAX_ATTEMPTS", 2)))
    overrides.setdefault("base_delay", float(getattr(s, "TASK_RETRY_BACKOFF_S", 5.0)))
    overrides.setdefault(
        "max_delay", float(getattr(s, "TASK_RETRY_MAX_BACKOFF_S", 60.0))
    )
    return _policy(**overrides)


# ---------------------------------------------------------------------------
# 退避
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    policy: Optional[RetryPolicy] = None,
    operation: str = "",
    sleep: Optional[Callable[[float], Awaitable[None]]] = None,
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
) -> T:
    """执行 ``func``，对**可重试**异常按策略重试；耗尽后抛 :class:`RetryExhausted`。

    Args:
        func: 零参数协程工厂（每次重试都会重新调用，确保重新发起请求）。
        policy: 重试策略，默认 :func:`default_policy`。
        operation: 日志与异常里显示的操作名。
        sleep: 注入的 sleep（测试用；默认 :func:`asyncio.sleep`）。
        on_retry: 每次重试前的回调 ``(attempt, exc, delay)``。

    Raises:
        RetryExhausted: 可重试错误耗尽全部尝试次数后抛出（``last_error`` 为原始异常）。
        BaseException: 不可重试的错误原样抛出，不做任何包装。
    """
    policy = policy or default_policy()
    attempts = policy.effective_attempts()
    sleep_fn = sleep or asyncio.sleep
    label = operation or getattr(func, "__qualname__", "call")

    if attempts <= 1:
        return await func()

    last_exc: Optional[BaseException] = None

    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 - 分类后再决定抛出/重试
            last_exc = exc

            if not is_retryable(exc):
                logger.debug(
                    f"[retry] {label} 第 {attempt} 次失败且不可重试"
                    f"（{type(exc).__name__}），直接抛出: {exc}"
                )
                raise

            if attempt >= attempts:
                logger.error(
                    f"[retry] {label} 已达重试上限（{attempts} 次），"
                    f"最后错误: {type(exc).__name__}: {exc}"
                )
                break

            delay = backoff_delay(attempt, policy)
            logger.warning(
                f"[retry] {label} 第 {attempt}/{attempts} 次失败"
                f"（{type(exc).__name__}: {exc}），{delay:.2f}s 后重试"
            )
            if on_retry is not None:
                maybe_awaitable = on_retry(attempt, exc, delay)
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable
            await sleep_fn(delay)

    assert last_exc is not None  # 循环内必然赋值（attempts >= 2）
    raise RetryExhausted(attempts=attempts, last_error=last_exc, operation=label)


async def retry_stream(
    make_stream: Callable[[], Awaitable[Any]],
    *,
    policy: Optional[RetryPolicy] = None,
    operation: str = "",
    sleep: Optional[Callable[[float], Awaitable[None]]] = None,
):
    """流式调用的重试包装：**只重试"首字节之前"的失败**。

    流式响应一旦吐出 token，重试就会让前端已渲染的内容被重复追加，因此约定：

    * 建立流（发起请求）失败 → 可重试；
    * 迭代过程中失败且**尚未**产出 token（如服务端在首个 chunk 前断开）→ 可重试；
    * 迭代过程中失败且**已产出** token → 直接抛出，不重试。

    Yields:
        原始流产出的每个 chunk；``make_stream`` 返回字符串时按单块产出。
    """
    policy = policy or llm_policy()
    attempts = policy.effective_attempts()
    sleep_fn = sleep or asyncio.sleep
    label = operation or "stream"
    total = max(1, attempts)

    for attempt in range(1, total + 1):
        emitted = False
        try:
            stream = await make_stream()
            if stream is None:
                return
            if isinstance(stream, str):
                yield stream
                return
            async for chunk in stream:
                emitted = True
                yield chunk
            return
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001
            # 已产出内容后不再重试（否则会重复渲染）
            retryable = is_retryable(exc) and not emitted

            if not retryable or attempt >= total:
                if retryable:
                    logger.error(
                        f"[retry] {label} 流式调用已达重试上限（{total} 次），"
                        f"最后错误: {type(exc).__name__}: {exc}"
                    )
                raise

            delay = backoff_delay(attempt, policy)
            logger.warning(
                f"[retry] {label} 流式调用第 {attempt}/{total} 次失败"
                f"（{type(exc).__name__}: {exc}），{delay:.2f}s 后重试"
            )
            await sleep_fn(delay)

def backoff_delay(attempt: int, policy: RetryPolicy) -> float:
    """计算第 ``attempt`` 次失败后、下一次尝试前的等待秒数。

    Args:
        attempt: 已失败的尝试序号（1 表示第一次失败）。
        policy: 重试策略。

    Returns:
        指数退避 + 抖动后的秒数，落在 ``[0, max_delay]``。
    """
    raw = policy.base_delay * (policy.backoff_factor ** max(0, attempt - 1))
    delay = min(raw, policy.max_delay)
    if policy.jitter > 0:
        delay *= 1.0 + random.uniform(-policy.jitter, policy.jitter)
    return round(max(0.0, min(delay, policy.max_delay)), 3)
