"""
Task base class.

所有任务需继承 TaskBase 并实现 run() 方法。
"""
import enum
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TaskBase(ABC):
    """任务基类。"""

    def __init__(self, task_id: Optional[str] = None):
        self.task_id: str = task_id or str(uuid.uuid4())
        self.status: TaskStatus = TaskStatus.PENDING
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.created_at: datetime = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    @abstractmethod
    async def run(self) -> Any:
        """执行任务。返回任务结果。"""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """序列化任务状态。"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }