"""
Sprint 29 Step 5: Background Worker Architecture 测试

测试:
1. 任务创建和基类功能
2. 任务执行（成功/失败）
3. 任务状态跟踪
4. DocumentEmbeddingTask 具体任务
5. submit_task 提交接口
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.services.tasks.base import TaskBase, TaskStatus
from app.services.tasks.local_worker import LocalWorker
from app.services.tasks.document_task import DocumentEmbeddingTask


class TestTaskBase:
    """TaskBase 基础功能测试"""

    def test_task_initial_state(self):
        """任务初始状态"""
        task = DocumentEmbeddingTask(
            document_id="doc-1",
            knowledge_base_id="kb-1",
            content="test content",
        )
        assert task.status == TaskStatus.PENDING
        assert task.task_id is not None
        assert task.error is None
        assert task.result is None
        print(f"[PASS] Task initial state: {task.status.value}")

    def test_task_id_uniqueness(self):
        """任务 ID 唯一"""
        task1 = DocumentEmbeddingTask("doc-1", "kb-1", "a")
        task2 = DocumentEmbeddingTask("doc-2", "kb-1", "b")
        assert task1.task_id != task2.task_id
        print(f"[PASS] Task ID unique: {task1.task_id} != {task2.task_id}")

    def test_task_to_dict(self):
        """任务序列化"""
        task = DocumentEmbeddingTask("doc-1", "kb-1", "content")
        d = task.to_dict()
        assert d["task_id"] == task.task_id
        assert d["status"] == "pending"
        assert d["error"] is None
        print(f"[PASS] Task to_dict: {d['status']}")


class TestDocumentEmbeddingTask:
    """DocumentEmbeddingTask 功能测试"""

    def test_task_attributes(self):
        """任务参数"""
        task = DocumentEmbeddingTask(
            document_id="doc-001",
            knowledge_base_id="kb-001",
            content="这是一段测试文档内容。" * 100,
            metadata={"source": "test"},
        )
        assert task.document_id == "doc-001"
        assert task.knowledge_base_id == "kb-001"
        assert task.metadata["source"] == "test"
        print(f"[PASS] DocumentEmbeddingTask attrs: doc={task.document_id}, kb={task.knowledge_base_id}")

    def test_task_run_result(self):
        """任务执行结果"""
        async def run():
            task = DocumentEmbeddingTask("doc-1", "kb-1", "hello world")
            result = await task.run()
            assert result["document_id"] == "doc-1"
            assert result["status"] == "embedded"
            assert result["chunks_count"] >= 1
            print(f"[PASS] Task run result: {result}")
        asyncio.run(run())


class TestLocalWorker:
    """LocalWorker 功能测试"""

    def test_submit_and_execute(self):
        """提交任务并执行"""
        async def run():
            worker = LocalWorker()
            task = DocumentEmbeddingTask("doc-1", "kb-1", "test content")

            task_id = worker.submit(task)
            assert task_id == task.task_id

            # 等待任务执行完成
            await asyncio.sleep(0.1)

            status = worker.get_status(task_id)
            assert status == TaskStatus.SUCCESS, f"Expected SUCCESS, got {status}"
            print(f"[PASS] Worker submit & execute: {status.value}")
        asyncio.run(run())

    def test_task_failure(self):
        """任务失败处理"""
        async def run():
            worker = LocalWorker()

            class FailingTask(TaskBase):
                async def run(self):
                    raise ValueError("模拟失败")

            task = FailingTask()
            task_id = worker.submit(task)
            await asyncio.sleep(0.1)

            status = worker.get_status(task_id)
            assert status == TaskStatus.FAILED, f"Expected FAILED, got {status}"

            stored = worker.get_task(task_id)
            assert "模拟失败" in stored.error
            print(f"[PASS] Worker task failure: {status.value}, error={stored.error}")
        asyncio.run(run())

    def test_list_tasks(self):
        """任务列表"""
        async def run():
            worker = LocalWorker()
            t1 = DocumentEmbeddingTask("doc-1", "kb-1", "a")
            t2 = DocumentEmbeddingTask("doc-2", "kb-1", "b")
            worker.submit(t1)
            worker.submit(t2)
            await asyncio.sleep(0.1)

            tasks = worker.list_tasks()
            assert len(tasks) == 2
            all_success = all(s == TaskStatus.SUCCESS for s in tasks.values())
            assert all_success, f"Not all success: {tasks}"
            print(f"[PASS] Worker list_tasks: {len(tasks)} tasks, all success")
        asyncio.run(run())

    def test_submit_task_function(self):
        """submit_task 便捷函数"""
        async def run():
            from app.services.tasks import submit_task, get_worker
            task = DocumentEmbeddingTask("doc-api", "kb-api", "api test")
            task_id = submit_task(task)
            await asyncio.sleep(0.1)

            stored = get_worker().get_task(task_id)
            assert stored is not None
            assert stored.status == TaskStatus.SUCCESS
            print(f"[PASS] submit_task function: {task_id} -> {stored.status.value}")
        asyncio.run(run())

    def test_get_task_not_found(self):
        """获取不存在的任务"""
        worker = LocalWorker()
        assert worker.get_task("nonexistent") is None
        assert worker.get_status("nonexistent") is None
        print("[PASS] Get nonexistent task returns None")


if __name__ == "__main__":
    print("=" * 50)
    print("Sprint 29 Step 5: Background Worker 测试")
    print("=" * 50)

    t1 = TestTaskBase()
    t1.test_task_initial_state()
    t1.test_task_id_uniqueness()
    t1.test_task_to_dict()

    t2 = TestDocumentEmbeddingTask()
    t2.test_task_attributes()
    t2.test_task_run_result()

    t3 = TestLocalWorker()
    t3.test_submit_and_execute()
    t3.test_task_failure()
    t3.test_list_tasks()
    t3.test_submit_task_function()
    t3.test_get_task_not_found()

    print("\n" + "=" * 50)
    print("所有测试通过!")
    print("=" * 50)