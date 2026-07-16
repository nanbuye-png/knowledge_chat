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
    """
    if not PSUTIL_AVAILABLE:
        return {
            "cpu_usage": None,
            "memory_usage": None,
            "disk_usage": None,
            "error": "psutil not installed",
        }

    try:
        cpu_percent = psutil.cpu_percent(interval=1)
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
