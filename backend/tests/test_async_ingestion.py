"""异步入库测试（P0-4）。

对应计划要求：
* Upload → Create Document → PENDING → Async Task → … → COMPLETED
* Document 状态机：PENDING / PROCESSING / COMPLETED / FAILED
* 任务执行不依赖请求生命周期（独立线程 + 独立事件循环）
"""
import asyncio
import os
import sys
import threading
import time

import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.models.document import Document, DocumentStatus  # noqa: E402
from app.services.tasks import DocumentProcessingTask  # noqa: E402
from app.services.tasks.base import TaskBase, TaskStatus  # noqa: E402
from app.services.tasks.local_worker import LocalWorker  # noqa: E402


# ---------------------------------------------------------------------------
# 1: 状态机
# ---------------------------------------------------------------------------


class TestDocumentStatus:
    def test_pending_exists(self):
        assert DocumentStatus.PENDING.value == "pending"
        assert {s.value for s in DocumentStatus} == {
            "pending",
            "processing",
            "completed",
            "failed",
        }
        print("[PASS] DocumentStatus 含 PENDING")


# ---------------------------------------------------------------------------
# 2: Worker 执行模型（独立线程 + 独立事件循环）
# ---------------------------------------------------------------------------


class _RecordingTask(TaskBase):
    def __init__(self, delay: float = 0.2):
        super().__init__()
        self.delay = delay
        self.thread_name = None

    async def run(self):
        self.thread_name = threading.current_thread().name
        await asyncio.sleep(self.delay)
        return "done"


class TestLocalWorker:
    def test_submit_returns_immediately(self):
        """提交必须立即返回，不能等任务跑完（回归：旧实现挂在调用方事件循环）。"""
        worker = LocalWorker()
        task = _RecordingTask(delay=0.5)

        start = time.monotonic()
        task_id = worker.submit(task)
        elapsed = time.monotonic() - start

        assert elapsed < 0.3, f"submit 不应阻塞，耗时 {elapsed:.2f}s"
        assert worker.wait(task_id, timeout=5) == TaskStatus.SUCCESS
        print(f"[PASS] submit 立即返回（{elapsed*1000:.0f}ms）")

    def test_task_runs_in_separate_thread(self):
        worker = LocalWorker()
        task = _RecordingTask(delay=0.05)
        task_id = worker.submit(task)
        worker.wait(task_id, timeout=5)

        assert task.thread_name is not None
        assert task.thread_name != threading.current_thread().name
        assert task.thread_name.startswith("kc-task-")
        print(f"[PASS] 任务在独立线程执行: {task.thread_name}")

    def test_task_survives_caller_loop_exit(self):
        """任务不能依赖调用方的事件循环（请求结束后仍要跑完）。"""

        async def submit_from_request():
            worker = LocalWorker()
            task = _RecordingTask(delay=0.3)
            return worker, worker.submit(task)

        worker, task_id = asyncio.run(submit_from_request())
        # 调用方的 asyncio.run 已经结束（事件循环已关闭）
        assert worker.wait(task_id, timeout=5) == TaskStatus.SUCCESS
        print("[PASS] 任务在请求事件循环结束后仍完成")

    def test_failure_is_recorded(self):
        class _FailingTask(TaskBase):
            async def run(self):
                raise RuntimeError("boom")

        worker = LocalWorker()
        task = _FailingTask()
        task_id = worker.submit(task)

        assert worker.wait(task_id, timeout=5) == TaskStatus.FAILED
        assert "boom" in (task.error or "")
        print("[PASS] 任务失败被记录")

    def test_concurrency_bound(self):
        worker = LocalWorker(max_concurrency=2)
        assert isinstance(worker._semaphore, threading.BoundedSemaphore)
        print("[PASS] 并发上限已配置")


# ---------------------------------------------------------------------------
# 3: 后台文档处理任务（状态流转）
# ---------------------------------------------------------------------------


def _add_document(temp_db, document_id="doc-1"):
    async def scenario():
        async with temp_db.session() as db:
            db.add(
                Document(
                    id=document_id,
                    filename="a.txt",
                    file_size=1,
                    file_type=".txt",
                    status=DocumentStatus.PENDING.value,
                    knowledge_base_id=1,
                )
            )
            await db.commit()

    asyncio.run(scenario())


async def _read_document_async(temp_db, document_id="doc-1"):
    """在**当前事件循环**内读取文档（不能在循环内调用 asyncio.run）。"""
    from sqlalchemy import select

    async with temp_db.session() as db:
        result = await db.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one()


def _read_document(temp_db, document_id="doc-1"):
    return asyncio.run(_read_document_async(temp_db, document_id))


def _patch_db(monkeypatch, temp_db):
    """让任务内部使用的 async_session 指向临时库。"""
    import app.storage.database as storage_module

    monkeypatch.setattr(storage_module, "async_session", temp_db.session)


class TestDocumentProcessingTask:
    def test_success_flow(self, temp_db, monkeypatch):
        """PENDING → PROCESSING → COMPLETED，并写入 chunk_count。"""
        seen_statuses: list[str] = []

        class _FakePipeline:
            async def process_document(self, context):
                # 处理期间的状态必须是 PROCESSING
                doc = await _read_document_async(temp_db, context.document_id)
                seen_statuses.append(doc.status)
                return 7

        monkeypatch.setattr(
            "app.services.knowledge.pipeline.KnowledgePipeline",
            lambda: _FakePipeline(),
        )
        _patch_db(monkeypatch, temp_db)

        _add_document(temp_db)
        task = DocumentProcessingTask(
            document_id="doc-1",
            file_path="/tmp/a.txt",
            filename="a.txt",
            knowledge_base_id=1,
        )
        result = asyncio.run(task.run())

        doc = _read_document(temp_db)
        assert seen_statuses == ["processing"], "处理中状态应为 processing"
        assert doc.status == "completed"
        assert doc.chunk_count == 7
        assert result["chunks_count"] == 7
        print(
            f"[PASS] 状态流转 PENDING → PROCESSING → COMPLETED（chunks={doc.chunk_count}）"
        )

    def test_failure_flow(self, temp_db, monkeypatch):
        """处理失败 → FAILED + error_message，并向上抛出（Worker 记录任务失败）。"""

        class _FailingPipeline:
            async def process_document(self, context):
                raise ValueError("文档内容为空，无法处理")

        monkeypatch.setattr(
            "app.services.knowledge.pipeline.KnowledgePipeline",
            lambda: _FailingPipeline(),
        )
        _patch_db(monkeypatch, temp_db)

        _add_document(temp_db)
        task = DocumentProcessingTask(
            document_id="doc-1",
            file_path="/tmp/a.txt",
            filename="a.txt",
            knowledge_base_id=1,
        )

        with pytest.raises(ValueError):
            asyncio.run(task.run())

        doc = _read_document(temp_db)
        assert doc.status == "failed"
        assert "无法处理" in (doc.error_message or "")
        print(f"[PASS] 失败流转 → FAILED（{doc.error_message}）")

    def test_missing_document_is_tolerated(self, temp_db, monkeypatch):
        """文档被删除后任务不应崩溃，只记录告警。"""
        _patch_db(monkeypatch, temp_db)
        task = DocumentProcessingTask(
            document_id="not-exist",
            file_path="/tmp/a.txt",
            filename="a.txt",
            knowledge_base_id=1,
        )
        asyncio.run(task._update_status(DocumentStatus.PROCESSING.value))
        print("[PASS] 文档不存在时状态更新安全跳过")


# ---------------------------------------------------------------------------
# 4: 上传路径（异步提交 vs 同步处理）
# ---------------------------------------------------------------------------


class _FakeUpload:
    """最小 UploadFile 替身（DocumentService 只用到 filename/read/seek）。"""

    def __init__(self, filename: str, content: bytes = b"hello world"):
        self.filename = filename
        self._buffer = content
        self._pos = 0

    async def read(self) -> bytes:
        data = self._buffer[self._pos :]
        self._pos = len(self._buffer)
        return data

    async def seek(self, pos: int) -> None:
        self._pos = pos


def _prepare_kb(temp_db, user_id: int = 1, kb_id: int = 1):
    async def scenario():
        from app.models.knowledge_base import KnowledgeBase
        from app.models.user import User

        async with temp_db.session() as db:
            db.add(
                User(
                    id=user_id,
                    username=f"user{user_id}",
                    password_hash="x",
                )
            )
            db.add(
                KnowledgeBase(id=kb_id, user_id=user_id, name="测试库")
            )
            await db.commit()

    asyncio.run(scenario())


class TestUploadPath:
    def _setup(self, monkeypatch, temp_db, tmp_path, async_mode: bool):
        from app.services import document_service as ds_module

        class _FakePipeline:
            def __init__(self):
                self.calls = 0

            async def process_document(self, context):
                self.calls += 1
                return 3

        pipeline = _FakePipeline()
        # 两处引用都要 patch：
        # 1) document_service 模块持有自己的 KnowledgePipeline 名称（同步路径用）
        # 2) 后台任务在 run() 内从源模块 import（异步路径用）
        monkeypatch.setattr(ds_module, "KnowledgePipeline", lambda: pipeline)
        monkeypatch.setattr(
            "app.services.knowledge.pipeline.KnowledgePipeline", lambda: pipeline
        )
        monkeypatch.setattr(ds_module.settings, "UPLOAD_DIR", str(tmp_path))
        monkeypatch.setattr(
            ds_module.settings, "DOCUMENT_PROCESSING_ASYNC", async_mode
        )
        _patch_db(monkeypatch, temp_db)

        from app.services.tasks import set_worker

        worker = LocalWorker()
        set_worker(worker)
        return pipeline, worker

    def test_async_upload_returns_pending(self, temp_db, tmp_path, monkeypatch):
        """异步模式：上传立即返回且状态为 PENDING，处理由后台完成。"""
        from app.services.document_service import DocumentService

        pipeline, worker = self._setup(monkeypatch, temp_db, tmp_path, async_mode=True)
        _prepare_kb(temp_db)

        async def scenario():
            async with temp_db.session() as db:
                return await DocumentService().upload_document(
                    _FakeUpload("a.txt"), db, user_id=1, knowledge_base_id=1
                )

        doc = asyncio.run(scenario())
        assert doc.status == "pending", "上传应立刻返回 pending 状态"

        task_ids = list(worker.list_tasks().keys())
        assert task_ids, "应提交一个后台任务"
        assert worker.wait(task_ids[0], timeout=10) == TaskStatus.SUCCESS

        refreshed = _read_document(temp_db, doc.id)
        assert refreshed.status == "completed"
        assert refreshed.chunk_count == 3
        print(
            "[PASS] 异步入库: 上传返回 pending → 后台完成 completed"
            f"（chunks={refreshed.chunk_count}）"
        )

    def test_sync_upload_completes_inline(self, temp_db, tmp_path, monkeypatch):
        """同步模式（DOCUMENT_PROCESSING_ASYNC=false）：请求内完成。"""
        from app.services.document_service import DocumentService

        pipeline, worker = self._setup(
            monkeypatch, temp_db, tmp_path, async_mode=False
        )
        _prepare_kb(temp_db)

        async def scenario():
            async with temp_db.session() as db:
                return await DocumentService().upload_document(
                    _FakeUpload("a.txt"), db, user_id=1, knowledge_base_id=1
                )

        doc = asyncio.run(scenario())
        assert doc.status == "completed"
        assert doc.chunk_count == 3
        assert worker.list_tasks() == {}, "同步模式不应提交后台任务"
        print("[PASS] 同步模式请求内完成")

    def test_sync_failure_marks_failed(self, temp_db, tmp_path, monkeypatch):
        """同步模式下解析失败 → FAILED + error_message（不再静默成功）。"""
        from app.services import document_service as ds_module
        from app.services.document_service import DocumentService

        class _FailingPipeline:
            async def process_document(self, context):
                raise ValueError("文档内容为空，无法处理")

        # document_service 持有自己的 KnowledgePipeline 引用，需 patch 它本身
        monkeypatch.setattr(ds_module, "KnowledgePipeline", lambda: _FailingPipeline())
        monkeypatch.setattr(ds_module.settings, "UPLOAD_DIR", str(tmp_path))
        monkeypatch.setattr(ds_module.settings, "DOCUMENT_PROCESSING_ASYNC", False)
        _patch_db(monkeypatch, temp_db)
        _prepare_kb(temp_db)

        async def scenario():
            async with temp_db.session() as db:
                return await DocumentService().upload_document(
                    _FakeUpload("a.txt"), db, user_id=1, knowledge_base_id=1
                )

        doc = asyncio.run(scenario())
        assert doc.status == "failed"
        assert "无法处理" in (doc.error_message or "")
        print(f"[PASS] 入库失败 → FAILED（{doc.error_message}）")

