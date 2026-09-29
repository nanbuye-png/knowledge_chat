"""Phase 3 §5.3 上传幂等的回归测试。

覆盖内容
--------
1. **内容指纹**：``file_hash`` 就是 SHA-256（64 位十六进制）。
2. **重复上传**：同一知识库内相同内容第二次上传被跳过 —— 不新建记录、
   不派发任务、临时文件被清理。
3. **不同内容 / 不同知识库**：正常新建记录（去重不能误伤）。
4. **失败记录复用**：命中 FAILED 记录时复用同一条记录重跑（清索引、
   重置 retry_count/error_message），而不是留下两条永远 FAILED 的记录。
5. **NULL 安全**：没有 file_hash 的历史记录可以并存（唯一约束允许多个 NULL）。
6. **契约**：``UploadResponse.skipped/duplicated_of`` 与审计留痕（status=SKIPPED）。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from typing import Optional

import pytest

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.models.document import Document, DocumentStatus  # noqa: E402
from app.schemas.document import DocumentResponse, UploadResponse  # noqa: E402


# ---------------------------------------------------------------------------
# 测试替身与工具
# ---------------------------------------------------------------------------


class _FakeUpload:
    """最小 UploadFile 替身（DocumentService 只用到 filename/read/seek）。"""

    def __init__(self, filename: str, content: bytes = b"same content"):
        self.filename = filename
        self._buffer = content
        self._pos = 0

    async def read(self) -> bytes:
        data = self._buffer[self._pos :]
        self._pos = len(self._buffer)
        return data

    async def seek(self, pos: int) -> None:
        self._pos = pos


class _FakePipeline:
    """可切换成功/失败的入库流水线替身。"""

    def __init__(self, chunk_count: int = 3, error: Optional[Exception] = None):
        self.chunk_count = chunk_count
        self.error = error
        self.calls = 0

    async def process_document(self, context) -> int:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.chunk_count


class _RecordingVectorStore:
    """记录被删除的文档 ID（验证"复用记录前先清索引"）。"""

    def __init__(self):
        self.deleted: list[str] = []

    async def delete_document(self, document_id: str) -> None:
        self.deleted.append(document_id)


class _RecordingSparseIndex:
    def __init__(self):
        self.deleted: list[str] = []

    async def delete_document(self, document_id: str) -> None:
        self.deleted.append(document_id)


def _prepare_kb(temp_db, kb_id: int = 1, user_id: int = 1):
    async def scenario():
        from sqlalchemy import select

        from app.models.knowledge_base import KnowledgeBase
        from app.models.user import User

        async with temp_db.session() as db:
            existing = await db.execute(select(User).where(User.id == user_id))
            if existing.scalar_one_or_none() is None:
                db.add(User(id=user_id, username=f"user{user_id}", password_hash="x"))
            db.add(KnowledgeBase(id=kb_id, user_id=user_id, name=f"库{kb_id}"))
            await db.commit()

    asyncio.run(scenario())


def _setup(monkeypatch, temp_db, tmp_path, pipeline, **settings_overrides):
    """把上传链路指向临时目录 + 临时库 + 假流水线（默认同步处理）。"""
    from app.services import document_service as ds_module

    vector_store = _RecordingVectorStore()
    sparse_index = _RecordingSparseIndex()

    monkeypatch.setattr(ds_module, "KnowledgePipeline", lambda: pipeline)
    monkeypatch.setattr(ds_module.document_service, "_pipeline", pipeline)
    monkeypatch.setattr(ds_module, "vector_store", vector_store)
    monkeypatch.setattr(
        "app.services.retrieval.sparse_index.get_sparse_index", lambda: sparse_index
    )
    monkeypatch.setattr(ds_module.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(ds_module.settings, "DOCUMENT_PROCESSING_ASYNC", False)
    monkeypatch.setattr(ds_module.settings, "DOCUMENT_DEDUP_ENABLED", True)
    for name, value in settings_overrides.items():
        monkeypatch.setattr(ds_module.settings, name, value)

    import app.storage.database as storage_module

    monkeypatch.setattr(storage_module, "async_session", temp_db.session)
    return vector_store, sparse_index


async def _upload(db, filename: str = "a.txt", content: bytes = b"same content", **kwargs):
    """调用上传服务，返回 :class:`UploadResult`。"""
    from app.services.document_service import DocumentService

    return await DocumentService().upload_document(
        _FakeUpload(filename, content), db, **kwargs
    )


def _upload_sync(temp_db, filename="a.txt", content=b"same content", **kwargs):
    async def scenario():
        async with temp_db.session() as db:
            return await _upload(db, filename, content, **kwargs)

    return asyncio.run(scenario())


def _fetch_documents(temp_db):
    async def scenario():
        from sqlalchemy import select

        async with temp_db.session() as db:
            result = await db.execute(select(Document).order_by(Document.created_at))
            return list(result.scalars().all())

    return asyncio.run(scenario())

# ---------------------------------------------------------------------------
# 1: 内容指纹
# ---------------------------------------------------------------------------


class TestContentFingerprint:
    def test_hash_is_sha256_hex(self):
        from app.services.document_service import DocumentService

        digest = DocumentService._compute_file_hash(b"hello")
        assert digest == hashlib.sha256(b"hello").hexdigest()
        assert len(digest) == 64
        assert DocumentService._compute_file_hash(b"hello") == digest
        assert DocumentService._compute_file_hash(b"hello!") != digest
        print(f"[PASS] file_hash = SHA-256（{digest[:12]}…，64 位）")


# ---------------------------------------------------------------------------
# 2: 重复上传被跳过
# ---------------------------------------------------------------------------


class TestDuplicateUpload:
    def test_same_content_is_skipped(self, temp_db, tmp_path, monkeypatch):
        pipeline = _FakePipeline(chunk_count=3)
        _setup(monkeypatch, temp_db, tmp_path, pipeline)
        _prepare_kb(temp_db)

        first = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)
        second = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)

        assert first.skipped is False
        assert second.skipped is True, "同知识库同内容应被跳过"
        assert second.duplicated_of == first.document.id
        assert second.document.id == first.document.id, "不应新建记录"

        docs = _fetch_documents(temp_db)
        assert len(docs) == 1, f"应只有 1 条记录，实际 {len(docs)}"
        assert pipeline.calls == 1, "重复上传不应触发第二次入库"

        # 重复上传的临时文件必须被清理，只留下既有记录对应的一份
        # （tmp_path 里还有 temp_db 的 test.db，所以只统计上传文件）
        stored = sorted(n for n in os.listdir(tmp_path) if n.endswith(".txt"))
        assert stored == [f"{first.document.id}.txt"], stored
        print("[PASS] 相同内容重复上传 → skipped=True，无新记录/新任务/残留文件")

    def test_different_content_creates_new_record(self, temp_db, tmp_path, monkeypatch):
        pipeline = _FakePipeline()
        _setup(monkeypatch, temp_db, tmp_path, pipeline)
        _prepare_kb(temp_db)

        first = _upload_sync(temp_db, content=b"content A", user_id=1, knowledge_base_id=1)
        second = _upload_sync(temp_db, content=b"content B", user_id=1, knowledge_base_id=1)

        assert first.skipped is False and second.skipped is False
        assert first.document.id != second.document.id
        assert len(_fetch_documents(temp_db)) == 2
        print("[PASS] 不同内容各自入库（去重不误伤）")

    def test_same_content_in_another_kb_is_new_record(self, temp_db, tmp_path, monkeypatch):
        pipeline = _FakePipeline()
        _setup(monkeypatch, temp_db, tmp_path, pipeline)
        _prepare_kb(temp_db, kb_id=1)
        _prepare_kb(temp_db, kb_id=2)

        first = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)
        second = _upload_sync(temp_db, user_id=1, knowledge_base_id=2)

        assert second.skipped is False, "去重作用域是单个知识库"
        assert first.document.id != second.document.id
        assert len(_fetch_documents(temp_db)) == 2
        print("[PASS] 同一内容上传到另一个知识库仍正常入库")

    def test_dedup_disabled_creates_duplicate(self, temp_db, tmp_path, monkeypatch):
        pipeline = _FakePipeline()
        _setup(
            monkeypatch,
            temp_db,
            tmp_path,
            pipeline,
            DOCUMENT_DEDUP_ENABLED=False,
        )
        _prepare_kb(temp_db)

        first = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)
        second = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)

        docs = _fetch_documents(temp_db)
        assert len(docs) == 2
        assert all(doc.file_hash is None for doc in docs), "关闭去重时不写指纹"
        assert second.skipped is False
        print("[PASS] DOCUMENT_DEDUP_ENABLED=false 时退化为原有行为")

# ---------------------------------------------------------------------------
# 3: 失败记录复用（不是留下两条 FAILED）
# ---------------------------------------------------------------------------


class TestFailedRecordReuse:
    def test_failed_record_is_reused_and_reprocessed(self, temp_db, tmp_path, monkeypatch):
        pipeline = _FakePipeline(error=RuntimeError("429 Too Many Requests"))
        vector_store, sparse_index = _setup(monkeypatch, temp_db, tmp_path, pipeline)
        _prepare_kb(temp_db)

        failed = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)
        assert failed.document.status == DocumentStatus.FAILED.value
        failed_id = failed.document.id

        # 第二次上传相同内容：这次让流水线成功
        pipeline.error = None
        retried = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)

        assert retried.document.id == failed_id, "应复用同一条 FAILED 记录"
        assert retried.skipped is False, "复用失败记录是「重跑」，不是「跳过」"
        assert retried.duplicated_of == failed_id
        assert retried.document.status == DocumentStatus.COMPLETED.value
        assert retried.document.chunk_count == 3
        assert retried.document.retry_count == 0, "重跑应重置重试计数"
        assert retried.document.error_message is None, "重跑应清掉旧错误"

        docs = _fetch_documents(temp_db)
        assert len(docs) == 1
        assert vector_store.deleted == [failed_id], "重跑前必须清掉旧向量"
        assert sparse_index.deleted == [failed_id], "重跑前必须清掉旧稀疏索引"
        print("[PASS] 命中 FAILED 记录 → 复用重跑（清索引 + 重置 retry_count）")

    def test_pending_record_is_treated_as_duplicate(self, temp_db, tmp_path, monkeypatch):
        """处理中的文档再上传同一内容 → 跳过（避免重复派发任务）。"""
        pipeline = _FakePipeline()
        _setup(monkeypatch, temp_db, tmp_path, pipeline)
        _prepare_kb(temp_db)

        first = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)

        # 人为把状态改回 PROCESSING（模拟后台还在跑）
        async def scenario():
            from sqlalchemy import select

            async with temp_db.session() as db:
                result = await db.execute(
                    select(Document).where(Document.id == first.document.id)
                )
                doc = result.scalar_one()
                doc.status = DocumentStatus.PROCESSING.value
                await db.commit()

        asyncio.run(scenario())

        second = _upload_sync(temp_db, user_id=1, knowledge_base_id=1)
        assert second.skipped is True
        assert pipeline.calls == 1, "处理中不应再次派发"
        print("[PASS] 处理中的文档重复上传 → 跳过")


# ---------------------------------------------------------------------------
# 4: NULL 安全 + 契约
# ---------------------------------------------------------------------------


class TestNullSafetyAndContract:
    def test_documents_without_hash_can_coexist(self, temp_db):
        """历史数据没有指纹（NULL），唯一约束不允许误伤它们。"""

        async def scenario():
            async with temp_db.session() as db:
                for i in range(3):
                    db.add(
                        Document(
                            id=f"legacy-{i}",
                            filename=f"legacy{i}.txt",
                            file_size=1,
                            file_type=".txt",
                            status=DocumentStatus.COMPLETED.value,
                            knowledge_base_id=1,
                            file_hash=None,
                        )
                    )
                await db.commit()  # 不应抛 IntegrityError

        asyncio.run(scenario())
        assert len(_fetch_documents(temp_db)) == 3
        print("[PASS] file_hash=NULL 的历史记录可以并存（唯一约束 NULL 安全）")

    def test_duplicate_hash_within_kb_is_rejected_by_db(self, temp_db):
        """唯一约束是幂等的最终防线（并发上传竞态由数据库兜底）。"""

        async def scenario():
            from sqlalchemy.exc import IntegrityError

            async with temp_db.session() as db:
                for i in range(2):
                    db.add(
                        Document(
                            id=f"dup-{i}",
                            filename=f"dup{i}.txt",
                            file_size=1,
                            file_type=".txt",
                            status=DocumentStatus.PENDING.value,
                            knowledge_base_id=1,
                            file_hash="a" * 64,
                        )
                    )
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()

        asyncio.run(scenario())
        print("[PASS] 同知识库 + 同 file_hash 被唯一约束拒绝")

    def test_upload_response_contract(self):
        payload = UploadResponse(
            message="已跳过",
            document_id="doc-1",
            filename="a.txt",
            status="completed",
            skipped=True,
            duplicated_of="doc-1",
        ).model_dump()
        assert payload["skipped"] is True
        assert payload["duplicated_of"] == "doc-1"
        # 默认值保持向后兼容（老前端只认这几个字段）
        assert UploadResponse(
            message="ok", document_id="d", filename="f"
        ).model_dump()["skipped"] is False
        print("[PASS] UploadResponse 新增 skipped / duplicated_of 且默认兼容")

    def test_document_response_exposes_retry_count(self):
        response = DocumentResponse(
            id="d",
            filename="f.txt",
            file_size=1,
            file_type=".txt",
            status="completed",
            retry_count=2,
        )
        assert response.retry_count == 2
        assert DocumentResponse(
            id="d", filename="f.txt", file_size=1, file_type=".txt", status="pending"
        ).retry_count == 0
        print("[PASS] DocumentResponse 暴露 retry_count")

# ---------------------------------------------------------------------------
# 5: HTTP 契约（POST /api/documents/upload）
# ---------------------------------------------------------------------------


class TestUploadEndpoint:
    def _prepare(self, temp_db, tmp_path, monkeypatch):
        """把上传链路换成假流水线 + 临时目录 + 假当前用户。"""
        from app.api import documents as documents_api
        from app.auth.deps import get_current_user
        from app.main import app
        from app.services import document_service as ds_module

        pipeline = _FakePipeline(chunk_count=3)
        monkeypatch.setattr(ds_module.document_service, "_pipeline", pipeline)
        monkeypatch.setattr(ds_module, "vector_store", _RecordingVectorStore())
        monkeypatch.setattr(
            "app.services.retrieval.sparse_index.get_sparse_index",
            lambda: _RecordingSparseIndex(),
        )
        monkeypatch.setattr(ds_module.settings, "UPLOAD_DIR", str(tmp_path))
        monkeypatch.setattr(ds_module.settings, "DOCUMENT_PROCESSING_ASYNC", False)
        monkeypatch.setattr(ds_module.settings, "DOCUMENT_DEDUP_ENABLED", True)

        # 直接按「路由实际引用的那个 get_db」覆盖：本套件里有测试会
        # importlib.reload(app.storage.database)，此时 conftest 里按当前模块
        # 取到的 get_db 可能已不是路由持有的那一个。
        async def _override_get_db():
            async with temp_db.session() as session:
                yield session

        monkeypatch.setitem(
            app.dependency_overrides, documents_api.get_db, _override_get_db
        )

        class _User:
            id = 1
            username = "tester"
            role = "USER"

        # 绕过 JWT：直接注入当前用户
        monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: _User())
        _prepare_kb(temp_db)
        return pipeline

    def test_second_upload_is_skipped_and_audited(
        self, client, temp_db, tmp_path, monkeypatch
    ):
        pipeline = self._prepare(temp_db, tmp_path, monkeypatch)
        payload = b"same content"

        first = client.post(
            "/api/documents/upload",
            params={"knowledge_base_id": 1},
            files={"file": ("a.txt", payload, "text/plain")},
        )
        assert first.status_code == 200, first.text
        assert first.json()["skipped"] is False

        second = client.post(
            "/api/documents/upload",
            params={"knowledge_base_id": 1},
            files={"file": ("a.txt", payload, "text/plain")},
        )
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["skipped"] is True
        assert body["duplicated_of"] == first.json()["document_id"]
        assert "已跳过" in body["message"]
        assert pipeline.calls == 1

        async def fetch_audits():
            from sqlalchemy import select

            from app.models.audit_log import AuditLog

            async with temp_db.session() as db:
                result = await db.execute(select(AuditLog).order_by(AuditLog.id))
                return list(result.scalars().all())

        statuses = [log.status for log in asyncio.run(fetch_audits())]
        assert statuses.count("SUCCESS") == 1
        assert statuses.count("SKIPPED") == 1, statuses
        print(f"[PASS] 重复上传 HTTP 契约：skipped=True，审计状态 {statuses}")


# ---APPEND---
