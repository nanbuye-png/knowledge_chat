import sys
from loguru import logger
from .config import settings


def setup_logging():
    """配置应用的结构化日志。"""
    logger.remove()

    # 控制台处理器
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        level=settings.LOG_LEVEL,
        colorize=True,
    )

    # 带轮转的文件处理器
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        compression="zip",
    )

    logger.info(f"Logging configured at level: {settings.LOG_LEVEL}")
    return logger