"""API Rate Limiter — 可替换的限流架构。

提供基于内存的滑动窗口限流器，以及抽象基类供未来 Redis 替换。

用法:
    from app.services.security.rate_limiter import MemoryRateLimiter

    limiter = MemoryRateLimiter()

    if limiter.check("key", limit=5, window_seconds=60):
        # 允许请求
        pass
    else:
        # 拒绝请求 (429)
        pass
"""

import time
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class _Window:
    """滑动窗口内的请求时间戳记录。"""

    timestamps: list[float] = field(default_factory=list)


class BaseRateLimiter(ABC):
    """限流器抽象基类。

    Sprint 29 可实现 RedisRateLimiter(BaseRateLimiter) 替换。
    """

    @abstractmethod
    def check(self, key: str, limit: int, window_seconds: int) -> bool:
        """检查指定 key 在时间窗口内的请求是否超过限制。

        Args:
            key: 限流键（如 IP、user_id+endpoint）
            limit: 窗口内允许的最大请求数
            window_seconds: 滑动窗口大小（秒）

        Returns:
            True: 允许请求
            False: 超过限制，应返回 429
        """
        ...

    @abstractmethod
    def clear(self, key: str | None = None) -> None:
        """清除限流记录。

        Args:
            key: 指定 key 的记录，None 表示清除全部。
        """
        ...


class MemoryRateLimiter(BaseRateLimiter):
    """基于内存的滑动窗口限流器。

    线程安全。适合单进程部署。Sprint 29 迁移到 Redis 后弃用。
    """

    def __init__(self) -> None:
        self._windows: dict[str, _Window] = defaultdict(_Window)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            window = self._windows[key]

            # 清理过期的时间戳
            window.timestamps = [t for t in window.timestamps if t > cutoff]

            if len(window.timestamps) >= limit:
                return False  # 超限

            window.timestamps.append(now)
            return True

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._windows.clear()
            else:
                self._windows.pop(key, None)


# 全局单例 — 整个应用生命周期内共享
rate_limiter: MemoryRateLimiter = MemoryRateLimiter()


# ---------------------------------------------------------------------------
# 统一限流入口（Phase 3 §5.4：三套实现合并为一套）
# ---------------------------------------------------------------------------


async def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, dict]:
    """统一的限流检查入口。

    审计 §5.4 记录了三套并行实现（``core/rate_limit`` 依赖、
    ``middleware/rate_limit`` 中间件、``services/rate_limit_service``），
    行为互不一致。现在全部收敛到本函数：

    * **多实例/多 worker 场景必须有 Redis** —— 否则每进程各算一份配额，
      真实限额会被放大到「进程数 × limit」；
    * Redis 不可用（或调用失败）时回退到 :class:`MemoryRateLimiter`
      （单进程滑动窗口），保证服务不中断；
    * 语义约定：``allowed=False`` 时调用方必须返回 429。

    Args:
        key: 限流键（如 ``rl:chat:u:1`` / ``rate:login:1.2.3.4``）。
        limit: 窗口内允许的请求数；``<= 0`` 表示不限制。
        window_seconds: 窗口大小（秒）。

    Returns:
        ``(allowed, info)``；``info`` 含实际生效的后端与当前计数，便于日志/调试。
    """
    if limit is None or limit <= 0:
        return True, {"backend": "disabled", "limit": limit}

    redis = None
    try:
        from ...core.redis import get_redis

        redis = await get_redis()
    except Exception as exc:  # pragma: no cover - 防御性
        logger.debug(f"获取 Redis 客户端失败，使用进程内限流: {exc}")

    if redis is not None:
        try:
            current = await redis.incr(key)
            if current == 1:
                # 首次计数才设置过期，避免每次请求都刷新窗口
                await redis.expire(key, window_seconds)
            ttl = await redis.ttl(key)
            allowed = current <= limit
            return allowed, {
                "backend": "redis",
                "current_count": current,
                "limit": limit,
                "remaining": max(0, limit - current),
                "reset_after": ttl if isinstance(ttl, int) and ttl > 0 else None,
            }
        except Exception as exc:
            logger.warning(f"Redis 限流失败，降级为进程内限流（key={key}）: {exc}")

    allowed = rate_limiter.check(key, limit, window_seconds)
    return allowed, {
        "backend": "memory",
        "limit": limit,
        "remaining": None,
        "degraded": True,
    }
