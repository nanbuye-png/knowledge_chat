"""限流兼容门面（Phase 3 §5.4：实现已合并到 security.rate_limiter）。

历史上这里是一套**独立**的 Redis 限流实现（``get_redis()`` + ``INCR``/``EXPIRE``），
与 ``core/rate_limit.py``（进程内滑动窗口）和 ``middleware/rate_limit.py``
（第三个调用点）行为不一致：同一个键在两条链路上会得到不同结论。

现在唯一实现是 :func:`app.services.security.rate_limiter.check_rate_limit`；
本模块只保留同名函数，供既有调用方（中间件等）按旧名导入，避免出现
"改了限流但只改了一半"的情况。
"""
from __future__ import annotations

from ..services.security.rate_limiter import check_rate_limit

__all__ = ["check_rate_limit"]
