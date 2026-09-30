"""时间工具 —— 统一 naive UTC（审计 §6.1-4）。

为什么需要这个模块
------------------
数据库里的时间列统一是 ``DateTime``（= ``TIMESTAMP WITHOUT TIME ZONE``），
而代码写入的是 ``datetime.now(timezone.utc)``（aware）：SQLite 会**静默丢掉
tzinfo**、PostgreSQL 按会话时区转换后落库，两者读回来都是 naive；比较时右边
却又是 aware 的 ``now``：

    user.locked_until > datetime.now(timezone.utc)
    # TypeError: can't compare offset-naive and offset-aware datetimes

结果就是审计里描述的现象：**账号锁定一旦触发，登录立即 500**（本该是 403），
``/api/auth/sessions``、``/api/admin/sessions``、管理员在线用户列表同理。

约定（新代码必须遵守）
----------------------
* **落库一律 naive UTC** —— 用 :func:`utcnow`；
* **比较前先归一** —— 用 :func:`as_naive_utc` 处理从库里取出来的值，
  不要再拿它和 ``datetime.now(timezone.utc)`` 直接比。

不改列类型（不加 ``timezone=True``）是刻意的：那需要迁移全部 26 张表，
收益只是"形状更好看"，而 naive UTC 语义已经足够且不引入时区漂移。
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """当前 UTC 时间（**naive**），与数据库列类型保持一致。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_naive_utc(value: datetime | None) -> datetime | None:
    """把任意来源的 datetime 归一到 naive UTC。

    * aware → 先转成 UTC 再去掉 tzinfo；
    * naive → 视为本来就是 UTC（历史数据就是这么存的），原样返回；
    * ``None`` → ``None``，便于调用方先判空再比较。

    Examples:
        >>> from datetime import datetime, timezone as tz
        >>> as_naive_utc(datetime(2026, 1, 1, 12, tzinfo=tz.utc))
        datetime.datetime(2026, 1, 1, 12, 0)
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
