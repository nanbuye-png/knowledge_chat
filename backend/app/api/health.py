"""健康检查（Phase 3 §5.6 Observability）。

审计 §5.6 实测问题：``/api/health`` 硬编码 ``"status": "healthy"``，从不探测
数据库 / 向量库 / Redis → Docker / K8s 探针形同虚设（依赖挂了也照样"健康"）。

这里改为**真实依赖探测**，并把结果结构化返回：

* ``database``     —— ``SELECT 1``（真实往返，含连接可用性）
* ``vector_store`` —— 集合是否已初始化（并尝试 count）
* ``embedding``    —— 嵌入模型是否已加载
* ``redis``        —— 可达性（不可达 = degraded，因为限流/缓存是 fail-open 降级）
* ``llm``          —— 按当前 ``LLM_PROVIDER`` 校验 Provider/模型/Key 是否自洽

约定：所有探测都带超时且**不抛异常** —— "探针本身失败"同样是有效信息，
必须能在响应里看到，而不是让健康检查 500。
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from loguru import logger

from ..core.config import settings
from ..core.context import get_request_id
from ..services.embedding_service import embedding_service

router = APIRouter(tags=["系统"])

_start_time = time.time()

#: 单个依赖探测的超时（秒）——探针不能比被测系统还慢
PROBE_TIMEOUT = 2.0


async def _probe_database() -> dict:
    from sqlalchemy import text

    from ..storage.database import async_session

    start = time.perf_counter()
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {
            "ok": True,
            "detail": settings.DATABASE_TYPE,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001 - 探测失败要变成数据而不是异常
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:200]}


async def _probe_vector_store() -> dict:
    from ..storage.vector_store import vector_store

    if not bool(getattr(vector_store, "_initialized", False)):
        return {"ok": False, "detail": "未初始化（启动初始化失败或为测试环境）"}

    detail = settings.VECTOR_STORE_TYPE
    collection = getattr(vector_store, "_collection", None)
    if collection is not None and hasattr(collection, "count"):
        try:
            detail = f"{settings.VECTOR_STORE_TYPE}, chunks={collection.count()}"
        except Exception as exc:  # pragma: no cover - 依赖具体实现
            detail = f"{settings.VECTOR_STORE_TYPE}, count 失败: {exc}"
    return {"ok": True, "detail": detail}


async def _probe_embedding() -> dict:
    initialized = bool(getattr(embedding_service, "_initialized", False))
    return {
        "ok": initialized,
        "detail": settings.EMBEDDING_MODEL if initialized else "模型未加载",
    }


async def _probe_redis() -> dict:
    from ..core.redis import get_redis

    client = await get_redis()
    if client is None:
        return {"ok": False, "detail": "不可达（限流/缓存 fail-open 降级）"}
    try:
        await client.ping()
        return {"ok": True, "detail": settings.REDIS_URL}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"ping 失败: {exc}"[:200]}


def _probe_llm_config() -> dict:
    issues = settings.check_llm_config()
    detail = f"{settings.LLM_PROVIDER}/{settings.LLM_MODEL}"
    if issues:
        detail += f"，问题: {'；'.join(issues)}"
    return {"ok": not issues, "detail": detail}


async def _run_probe(name: str, coro) -> tuple[str, dict]:
    """执行单个探测，超时/异常都转成 ``{"ok": False}`` 结构。"""
    try:
        return name, await asyncio.wait_for(coro, timeout=PROBE_TIMEOUT)
    except asyncio.TimeoutError:
        return name, {"ok": False, "detail": f"探测超时（>{PROBE_TIMEOUT}s）"}
    except Exception as exc:  # pragma: no cover - 防御性
        logger.warning(f"健康探测异常 {name}: {exc}")
        return name, {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:200]}


@router.get("/api/health", summary="健康检查")
async def health_check():
    """系统健康检查：真实探测各依赖，给出可被探针消费的状态。"""
    results = await asyncio.gather(
        _run_probe("database", _probe_database()),
        _run_probe("vector_store", _probe_vector_store()),
        _run_probe("embedding", _probe_embedding()),
        _run_probe("redis", _probe_redis()),
    )
    checks = dict(results)
    checks["llm"] = _probe_llm_config()

    if not checks["database"]["ok"]:
        status = "unhealthy"
    elif all(check["ok"] for check in checks.values()):
        status = "healthy"
    else:
        status = "degraded"

    uptime_seconds = int(time.time() - _start_time)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60

    return {
        "status": status,
        "version": settings.APP_VERSION,
        "app_name": settings.APP_NAME,
        # 兼容字段：老前端 / 探针按这两个布尔值判断
        "embedding_model": checks["embedding"]["ok"],
        "llm_configured": checks["llm"]["ok"],
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": get_request_id(),
        "checks": checks,
    }
