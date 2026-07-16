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