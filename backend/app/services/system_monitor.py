try:
    import psutil  # type: ignore
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from datetime import datetime, timezone


def get_system_metrics() -> dict:
    """获取系统资源使用情况。

    Returns:
        dict 包含 cpu_usage, memory_usage, disk_usage

    注意：``psutil.cpu_percent(interval=1)`` 会**同步阻塞 1 秒**，在 async 处理器
    里调用等于把整个事件循环卡住 1 秒（审计 §5.6）。这里改为非阻塞采样：
    ``interval=None`` 返回自上次调用以来的平均使用率（首次调用返回 0.0）。
    """
    if not PSUTIL_AVAILABLE:
        return {
            "cpu_usage": None,
            "memory_usage": None,
            "disk_usage": None,
            "error": "psutil not installed",
        }

    try:
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "cpu_usage": cpu_percent,
            "memory_usage": memory.percent,
            "disk_usage": disk.percent,
        }
    except Exception as e:
        return {
            "cpu_usage": None,
            "memory_usage": None,
            "disk_usage": None,
            "error": str(e),
        }
