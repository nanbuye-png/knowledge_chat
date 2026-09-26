"""
LocalWorker - 本地异步任务执行器。

执行模型（P0-4）
----------------
每个任务跑在**独立的后台线程 + 独立事件循环**里：

* 上传请求提交任务后立即返回，任务不依赖请求的生命周期；
* 并发上限由 ``WORKER_MAX_CONCURRENCY`` 控制（超出则排队等待）；
* 任务状态与结果保存在内存字典中（进程级），供状态查询与测试使用；
* 未来可替换为 CeleryWorker 实现跨进程调度。

历史问题：旧实现用 ``asyncio.ensure_future`` 把任务挂在**请求所在的事件循环**
上，请求结束（连接断开、超时）后任务可能被取消 —— 这正是"上传后状态永远
停在 PROCESSING"的原因之一（审计 §5.1）。
"""
import asyncio
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from loguru import logger

from .base import TaskBase, TaskStatus


class LocalWorker:
    """本地 Worker：每个任务在独立线程的事件循环中执行。"""

    def __init__(self, max_concurrency: int = 4):
        self._tasks: Dict[str, TaskBase] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrency))

    # ------------------------------------------------------------------
    # 提交
    # ------------------------------------------------------------------

    def submit(self, task: TaskBase) -> str:
        """提交任务并立即返回 ``task_id``（不阻塞调用方）。"""
        with self._lock:
            self._tasks[task.task_id] = task

        thread = threading.Thread(
            target=self._run_in_thread,
            args=(task,),
            name=f"kc-task-{task.task_id[:8]}",
            daemon=True,
        )
        with self._lock:
            self._threads[task.task_id] = thread
        thread.start()

        logger.info(
            f"任务已提交: {task.task_id} ({type(task).__name__}) "
            f"thread={thread.name}"
        )
        return task.task_id

    def _run_in_thread(self, task: TaskBase) -> None:
        """在独立线程中运行任务（拥有自己的事件循环）。"""
        with self._semaphore:
            try:
                asyncio.run(self._execute(task))
            except Exception as exc:  # pragma: no cover - 防御性
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                task.completed_at = task.completed_at or datetime.utcnow()
                logger.error(f"任务线程异常: {task.task_id} - {exc}")

    async def _execute(self, task: TaskBase) -> None:
        """执行任务并更新状态。"""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()

        try:
            logger.info(f"任务开始执行: {task.task_id}")
            result = await task.run()
            task.status = TaskStatus.SUCCESS
            task.result = result
            logger.info(f"任务执行成功: {task.task_id}")
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.exception(f"任务执行失败: {task.task_id} - {e}")
        finally:
            task.completed_at = datetime.utcnow()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[TaskBase]:
        """获取任务对象。"""
        return self._tasks.get(task_id)

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态枚举。"""
        task = self._tasks.get(task_id)
        return task.status if task else None

    def list_tasks(self) -> Dict[str, TaskStatus]:
        """列出所有任务及其状态。"""
        return {tid: task.status for tid, task in self._tasks.items()}

    def wait(self, task_id: str, timeout: float = 30.0) -> Optional[TaskStatus]:
        """等待任务结束（轮询），返回最终状态；超时返回当前状态。

        供测试与优雅关闭路径使用，不参与业务主链路。
        """
        deadline = time.monotonic() + timeout
        terminal = {TaskStatus.SUCCESS, TaskStatus.FAILED}

        while time.monotonic() < deadline:
            status = self.get_status(task_id)
            if status in terminal:
                return status
            time.sleep(0.02)

        return self.get_status(task_id)
