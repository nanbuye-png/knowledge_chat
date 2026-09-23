import sys
from loguru import logger
from .config import settings


def _console_sink():
    """返回编码安全的控制台输出流。

    Windows 控制台默认使用 GBK 编码，无法编码日志中的 emoji 字符
    （如 🔗 / ⚠️），loguru 会因此抛出 UnicodeEncodeError 并打印大量
    ``--- Logging error ---`` traceback，掩盖真正的启动日志。
    这里在检测到当前编码无法输出 emoji 时，将标准输出切换为
    UTF-8（errors="replace"），保证日志不中断。
    """
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        "⚠️".encode(encoding)
        return stream
    except (UnicodeEncodeError, LookupError):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
        return stream


def setup_logging():
    """配置应用的结构化日志。"""
    logger.remove()

    # 控制台处理器
    logger.add(
        _console_sink(),
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
        encoding="utf-8",
    )

    logger.info(f"Logging configured at level: {settings.LOG_LEVEL}")
    return logger
