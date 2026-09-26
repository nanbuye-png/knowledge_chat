"""Redis async client — singleton with graceful degradation.

Why this module looks the way it does (P0-1)
--------------------------------------------
``redis-py``'s :class:`Connection` only accepts RESP2 (``protocol=2``) or
RESP3 (``protocol=3``); any other value raises **at connection
construction time**::

    >>> redis.asyncio.Connection(protocol=1)
    ConnectionError: protocol must be either 2 or 3

Historically this module passed ``protocol=1``, so :func:`get_redis`
could never hand out a working client and returned ``None`` forever —
every Redis-backed feature (rate limiting, cache) silently degraded to
"always allowed / always miss".  ``REDIS_PROTOCOL`` is therefore a
module-level constant guarded by a regression test.

Failure handling
----------------
* Connection errors never propagate: :func:`get_redis` returns ``None``
  so the application keeps serving (graceful degradation).
* After a failure Redis is marked unavailable for
  ``REDIS_RETRY_COOLDOWN_SECONDS``; during that window :func:`get_redis`
  returns immediately instead of re-attempting a TCP connect on every
  request (previously each request could block up to the socket timeout).
"""
from __future__ import annotations

import time
from typing import Any, Optional

from loguru import logger

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on environment
    aioredis = None  # type: ignore[assignment]
    REDIS_AVAILABLE = False

from ..core.config import settings

#: RESP protocol version — must be ``2`` (RESP2) or ``3`` (RESP3).
#: RESP2 keeps compatibility with Redis servers lacking the RESP3 HELLO.
REDIS_PROTOCOL: int = 2

#: Connect / read timeout in seconds.
REDIS_SOCKET_TIMEOUT: float = 3.0

#: How long to stop retrying after a failed connection attempt (seconds).
REDIS_RETRY_COOLDOWN_SECONDS: float = 30.0

_redis_client: Optional[Any] = None
_unavailable_until: float = 0.0


def build_client_kwargs() -> dict:
    """Return the keyword arguments used to construct the Redis client.

    Exposed as a function so tests can assert connection parameters
    (notably ``protocol``) without needing a running Redis server.
    """
    return {
        "encoding": "utf-8",
        "decode_responses": True,
        "protocol": REDIS_PROTOCOL,
        "socket_connect_timeout": REDIS_SOCKET_TIMEOUT,
        "socket_timeout": REDIS_SOCKET_TIMEOUT,
    }


async def get_redis():
    """获取 Redis 异步客户端（单例）。
    
    如果 Redis 不可用或未安装，返回 None 以支持优雅降级。
    """
    global _redis_client, _unavailable_until
    if _redis_client is not None:
        return _redis_client

    if not REDIS_AVAILABLE:
        return None

    # 最近一次连接失败 → 冷却期内直接返回，避免每个请求都白等连接超时
    if time.monotonic() < _unavailable_until:
        return None

    try:
        client = aioredis.from_url(settings.REDIS_URL, **build_client_kwargs())
        # 测试连接成功后才对外提供
        await client.ping()
        _redis_client = client
        _unavailable_until = 0.0
        logger.info(f"Redis 连接成功: {settings.REDIS_URL}")
        return _redis_client
    except Exception as exc:
        # 优雅降级：记录一次、进入冷却期、继续对外服务
        _unavailable_until = time.monotonic() + REDIS_RETRY_COOLDOWN_SECONDS
        logger.warning(
            f"Redis 不可达（{settings.REDIS_URL}），{REDIS_RETRY_COOLDOWN_SECONDS:.0f}s 内不再重试；"
            f"依赖 Redis 的能力（如限流）当前处于降级状态: {exc}"
        )
        return None


async def close_redis() -> None:
    """关闭 Redis 连接并清空单例与冷却状态。"""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"关闭 Redis 连接时出错: {exc}")
        finally:
            _redis_client = None

    reset_redis_state()


def reset_redis_state() -> None:
    """重置模块级状态（单例 + 冷却计时）。供测试与关闭流程使用。"""
    global _redis_client, _unavailable_until
    _redis_client = None
    _unavailable_until = 0.0
