"""客户端 IP 解析（Phase 3 §5.4）。

审计 §5.4 的实测问题：限流取 ``X-Forwarded-For`` 的**第一个**值，而 nginx 用
``$proxy_add_x_forwarded_for`` 会把客户端自带的字段原样保留在最左侧 ——
客户端只要自造一个 XFF 就能伪装成任意 IP，从而绕过登录限流与账号锁定。

正确做法：按"信任 N 层代理"从**右往左**取值：

    X-Forwarded-For: <客户端伪造>, <真实客户端 IP>
                                    ^ 由我们信任的代理追加，取它

``TRUSTED_PROXY_COUNT`` 默认 1（一层 nginx）。无 XFF（直连）时使用
``request.client.host``。
"""
from __future__ import annotations

from fastapi import Request

from .config import settings


def client_ip(request: Request) -> str:
    """返回可信的客户端 IP（用于限流键与审计日志）。"""
    forwarded = request.headers.get("X-Forwarded-For")
    trusted = max(1, int(getattr(settings, "TRUSTED_PROXY_COUNT", 1)))

    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            index = len(hops) - trusted
            return hops[index] if index >= 0 else hops[0]

    client = getattr(request, "client", None)
    return client.host if client else "unknown"
