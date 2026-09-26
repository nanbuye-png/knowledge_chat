"""
Task worker package.

提供任务抽象层，支持 LocalWorker（默认）和未来 CeleryWorker。
业务代码通过 submit_task() 提交异步任务。
"""
from typing import Optional

from .base import TaskBase, TaskStatus
from .document_task import DocumentEmbeddingTask, DocumentProcessingTask
from .local_worker import LocalWorker

# 默认使用本地 Worker
_worker_instance: Optional[LocalWorker] = None


def get_worker() -> LocalWorker:
    """获取当前 Worker 实例。"""
    global _worker_instance
    if _worker_instance is None:
        from ...core.config import settings

        _worker_instance = LocalWorker(
            max_concurrency=getattr(settings, "WORKER_MAX_CONCURRENCY", 4)
        )
    return _worker_instance


def set_worker(worker) -> None:
    """设置 Worker 实例（用于工厂注入）。"""
    global _worker_instance
    _worker_instance = worker


def submit_task(task: TaskBase) -> str:
    """提交任务到 Worker。"""
    return get_worker().submit(task)


__all__ = [
    "TaskBase",
    "TaskStatus",
    "LocalWorker",
    "DocumentEmbeddingTask",
    "DocumentProcessingTask",
    "get_worker",
    "set_worker",
    "submit_task",
]