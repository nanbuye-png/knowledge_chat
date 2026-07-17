"""
LocalWorker - 本地异步任务执行器。

使用 asyncio 在当前进程中执行任务。适合开发/测试环境。
未来可替换为 CeleryWorker 实现分布式任务调度。
"""
import asyncio
import time
from datetime import datetime
from typing import Dict, Optional

from loguru import logger

from .base import TaskBase, TaskStatus


class LocalWorker:
    """本地 Worker：在独立线程中异步执行任务。"""

    def __init__(self):
        self._tasks: Dict[str, TaskBase] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def submit(self, task: TaskBase) -> str:
        """提交任务。返回 task_id。"""
        self._tasks[task.task_id] = task
        logger.info(f"任务已提交: {task.task_id} ({type(task).__name__})")
        self._run_async(task)
        return task.task_id

    def _run_async(self, task: TaskBase) -> None:
        """在事件循环中执行任务。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 已有运行中的事件循环，创建任务
            asyncio.ensure_future(self._execute(task))
        else:
            # 无运行中事件循环，新建
            asyncio.run(self._execute(task))

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
            logger.error(f"任务执行失败: {task.task_id} - {e}")
        finally:
            task.completed_at = datetime.utcnow()

    def get_task(self, task_id: str) -> Optional[TaskBase]:
        """获取任务状态。"""
        return self._tasks.get(task_id)

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态枚举。"""
        task = self._tasks.get(task_id)
        return task.status if task else None

    def list_tasks(self) -> Dict[str, TaskStatus]:
        """列出所有任务及其状态。"""
        return {tid: task.status for tid, task in self._tasks.items()}