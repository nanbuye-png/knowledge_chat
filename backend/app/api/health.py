from fastapi import APIRouter
from loguru import logger
from datetime import datetime
import time

from ..core.config import settings
from ..services.embedding_service import embedding_service

router = APIRouter(tags=["系统"])

_start_time = time.time()


@router.get("/api/health", summary="健康检查")
async def health_check():
    """系统健康检查接口。"""
    uptime_seconds = int(time.time() - _start_time)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60

    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "app_name": settings.APP_NAME,
        "embedding_model": embedding_service._initialized if hasattr(embedding_service, '_initialized') else False,
        "llm_configured": bool(settings.DEEPSEEK_API_KEY),
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "timestamp": datetime.utcnow().isoformat(),
    }