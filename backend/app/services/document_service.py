import hashlib
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import UploadFile, HTTPException

from ..core.config import settings
from ..models.document import Document, DocumentStatus
from ..models.knowledge_base import KnowledgeBase
from ..schemas.document import DocumentResponse, DocumentListResponse
from ..storage.vector_store import vector_store
from .metrics import track_document_dedup

from .knowledge.context import KnowledgePipelineContext  # noqa: F401 - 对外可见（兼容既有引用）
from .knowledge.pipeline import KnowledgePipeline


@dataclass
class UploadResult:
    """上传结果（Phase 3 §5.3 幂等）。

    Attributes:
        document: 命中或新建的文档记录。
        skipped: ``True`` 表示同一知识库内已有相同内容 —— 本次**没有**新建记录、
            也没有派发新的处理任务。
        duplicated_of: 复用既有记录时指向该文档 ID（等于 ``document.id``）；
            ``skipped=False`` 但带值表示"复用了 FAILED 记录并重跑"。
    """

    document: Document
    skipped: bool = False
    duplicated_of: Optional[str] = None


class DocumentService:
    """Service for document management.

    File handling + DB operations stay here.
    AI processing (parse → chunk → embed → store) is delegated to
    :class:`KnowledgePipeline`.
    """

    def __init__(self):
        self._pipeline = KnowledgePipeline()

    async def upload_document(
        self, file: UploadFile, db: AsyncSession, user_id: int, knowledge_base_id: int
    ) -> UploadResult:
        """Upload and process a document（Phase 3 §5.3：内容级幂等）。

        Args:
            file: The uploaded file.
            db: Database session.
            user_id: The current user's ID.
            knowledge_base_id: The target knowledge base ID (must belong to the user).

        Returns:
            :class:`UploadResult`；``skipped=True`` 表示同一知识库内已有相同内容，
            本次未新建记录、未派发任务。
        """
        # Validate file
        await self._validate_file(file)

        # Verify knowledge_base belongs to user
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        kb = result.scalar_one_or_none()
        if kb is None:
            raise HTTPException(status_code=403, detail="无权访问该知识库")

        file_ext = os.path.splitext(file.filename)[1].lower()
        content = await file.read()
        file_size = len(content)
        file_hash = (
            self._compute_file_hash(content)
            if getattr(settings, "DOCUMENT_DEDUP_ENABLED", True)
            else None
        )

        # 幂等检查（在写盘之前）：同知识库 + 同内容 → 复用既有记录
        if file_hash:
            existing = await self._find_by_hash(db, knowledge_base_id, file_hash)
            if existing is not None:
                return await self._handle_existing(
                    existing, content, file_ext, knowledge_base_id, db
                )

        # Save file
        file_id = str(uuid.uuid4())
        file_path = os.path.join(settings.UPLOAD_DIR, f"{file_id}{file_ext}")
        with open(file_path, "wb") as f:
            f.write(content)

        # Create document record（PENDING：等待后台 Worker 处理）
        doc = Document(
            id=file_id,
            filename=file.filename,
            file_size=file_size,
            file_type=file_ext,
            status=DocumentStatus.PENDING.value,
            knowledge_base_id=knowledge_base_id,
            file_hash=file_hash,
        )
        db.add(doc)
        try:
            await db.commit()
        except IntegrityError:
            # 并发上传同一内容的竞态：由 uq_documents_kb_file_hash 兜底，
            # 应用层「先查后写」无法覆盖这个窗口。
            await db.rollback()
            self._remove_file(file_path)
            existing = (
                await self._find_by_hash(db, knowledge_base_id, file_hash)
                if file_hash
                else None
            )
            if existing is None:
                logger.error(
                    f"上传冲突但查不到既有记录: kb={knowledge_base_id}, hash={file_hash}"
                )
                raise HTTPException(
                    status_code=409, detail="文档正在被并发上传，请稍后重试"
                )
            logger.warning(
                f"并发上传同一内容，命中唯一约束，返回既有记录: "
                f"{existing.filename}（{existing.id}）"
            )
            return UploadResult(
                document=existing, skipped=True, duplicated_of=existing.id
            )

        await db.refresh(doc)
        track_document_dedup("created")

        # Dispatch processing (P0-4)
        await self._dispatch_or_process(doc, file_path, knowledge_base_id, db)
        return UploadResult(document=doc)

    # ------------------------------------------------------------------
    # 幂等辅助（Phase 3 §5.3）
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_file_hash(content: bytes) -> str:
        """内容指纹：SHA-256（64 位十六进制）。"""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    async def _find_by_hash(
        db: AsyncSession, knowledge_base_id: int, file_hash: str
    ) -> Optional[Document]:
        """按「知识库 + 内容指纹」查找既有记录（唯一约束保证最多一条）。"""
        result = await db.execute(
            select(Document)
            .where(
                Document.knowledge_base_id == knowledge_base_id,
                Document.file_hash == file_hash,
            )
            .order_by(Document.created_at.desc())
        )
        return result.scalars().first()

    async def _handle_existing(
        self,
        existing: Document,
        content: bytes,
        file_ext: str,
        knowledge_base_id: int,
        db: AsyncSession,
    ) -> UploadResult:
        """命中相同内容：非 FAILED 直接跳过；FAILED 则复用记录重跑。"""
        if existing.status != DocumentStatus.FAILED.value:
            logger.info(
                f"幂等命中：{existing.filename}（document_id={existing.id}, "
                f"status={existing.status}）内容与本次上传相同，跳过重复处理"
            )
            track_document_dedup("skipped")
            return UploadResult(
                document=existing, skipped=True, duplicated_of=existing.id
            )

        # 之前失败的文档：复用同一条记录重跑，而不是留下两条永远 FAILED 的记录。
        # 文件路径由文档 id 推导（uploads/{id}{ext}），因此把新内容写到既有记录的
        # 路径上，保持「记录 id ↔ 文件路径」一致。
        logger.info(f"幂等命中失败记录，复用并重跑: {existing.filename}（{existing.id}）")
        track_document_dedup("reused_failed")
        existing_path = os.path.join(
            settings.UPLOAD_DIR, f"{existing.id}{file_ext or existing.file_type}"
        )
        with open(existing_path, "wb") as f:
            f.write(content)

        # 上一轮可能已写入部分向量/稀疏索引，先清理以免出现重复 chunk
        await self._purge_indexes(existing.id)
        # 索引已变化 → 该知识库的检索缓存立即失效（避免重跑期间命中旧结果）
        await self._invalidate_retrieval_cache(knowledge_base_id)

        existing.file_type = file_ext or existing.file_type
        existing.file_size = len(content)
        existing.status = DocumentStatus.PENDING.value
        existing.chunk_count = 0
        existing.retry_count = 0
        existing.error_message = None
        await db.commit()
        await db.refresh(existing)

        await self._dispatch_or_process(existing, existing_path, knowledge_base_id, db)
        return UploadResult(document=existing, duplicated_of=existing.id)

    async def _dispatch_or_process(
        self, doc: Document, file_path: str, knowledge_base_id: int, db: AsyncSession
    ) -> None:
        """按配置决定异步派发（后台 Worker）还是请求内同步处理。"""
        if getattr(settings, "DOCUMENT_PROCESSING_ASYNC", True):
            self._dispatch_async(doc, file_path, knowledge_base_id)
        else:
            await self._process_inline(doc, file_path, knowledge_base_id, db)

    @staticmethod
    def _remove_file(path: str) -> None:
        """删除落盘的临时文件（失败只记录，不影响上传结果）。"""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError as exc:  # pragma: no cover - 防御性
            logger.warning(f"清理临时文件失败（{path}）: {exc}")

    async def _purge_indexes(self, document_id: str) -> None:
        """删除该文档的向量/稀疏索引（重复处理前调用，避免重复 chunk）。"""
        try:
            await vector_store.delete_document(document_id)
        except Exception as exc:  # noqa: BLE001 - 清理失败不应中断主流程
            logger.warning(f"清理向量索引失败（{document_id}）: {exc}")
        try:
            from .retrieval.sparse_index import get_sparse_index

            await get_sparse_index().delete_document(document_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"清理稀疏索引失败（{document_id}）: {exc}")

    @staticmethod
    async def _invalidate_retrieval_cache(knowledge_base_id: int) -> None:
        """让该知识库的检索缓存失效（Phase 3 §5.4）。"""
        try:
            from .cache.retrieval_cache import RetrievalCache

            await RetrievalCache().invalidate_knowledge_base(knowledge_base_id)
        except Exception as exc:  # noqa: BLE001 - 缓存失效失败不影响主流程
            logger.warning(f"检索缓存失效失败（kb={knowledge_base_id}）: {exc}")

    def _dispatch_async(self, doc, file_path: str, knowledge_base_id: int) -> None:
        """把处理任务交给后台 Worker；提交失败则降级为请求内同步处理。"""
        from .tasks import DocumentProcessingTask, submit_task

        try:
            task = DocumentProcessingTask(
                document_id=doc.id,
                file_path=file_path,
                filename=doc.filename,
                knowledge_base_id=knowledge_base_id,
            )
            task_id = submit_task(task)
            logger.info(
                f"文档已加入后台处理队列: {doc.filename} "
                f"(document_id={doc.id}, task_id={task_id})"
            )
        except Exception as exc:  # noqa: BLE001 - 提交失败必须可降级
            logger.warning(
                f"后台任务提交失败（将退回同步处理）: {exc}"
            )
            import asyncio

            asyncio.get_event_loop().create_task(
                self._process_inline(doc, file_path, knowledge_base_id, None)
            )

    async def _process_inline(self, doc, file_path: str, knowledge_base_id: int, db):
        """在请求内同步处理（DOCUMENT_PROCESSING_ASYNC=false 或降级路径）。"""
        from .knowledge.context import KnowledgePipelineContext

        doc.status = DocumentStatus.PROCESSING.value
        try:
            context = KnowledgePipelineContext(
                file_path=file_path,
                document_id=doc.id,
                filename=doc.filename,
                knowledge_base_id=knowledge_base_id,
            )
            chunk_count = await self._pipeline.process_document(context)

            doc.status = DocumentStatus.COMPLETED.value
            doc.chunk_count = chunk_count

        except Exception as e:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = str(e)[:500]
            logger.error(f"Document processing failed: {doc.filename} - {e}")

        if db is not None:
            await db.commit()

    async def _validate_file(self, file: UploadFile):
        """Validate file type and size."""
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {ext}。支持的类型: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )

        # Check file size
        content = await file.read()
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件过大。最大支持: {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
            )
        # Reset file position for later read
        await file.seek(0)

    async def get_documents(self, db: AsyncSession, knowledge_base_id: int, user_id: int) -> DocumentListResponse:
        """Get documents for a specific knowledge base (must belong to user)."""
        # Verify KB ownership
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        kb = result.scalar_one_or_none()
        if kb is None:
            raise HTTPException(status_code=403, detail="无权访问该知识库")

        result = await db.execute(
            select(Document)
            .where(Document.knowledge_base_id == knowledge_base_id)
            .order_by(Document.created_at.desc())
        )
        documents = result.scalars().all()
        items = [DocumentResponse(**doc.to_dict()) for doc in documents]
        return DocumentListResponse(documents=items, total=len(items))

    async def delete_document(self, document_id: str, db: AsyncSession, user_id: int):
        """Delete a document and its vector data (must belong to user)."""
        # Get document with KB ownership verification
        result = await db.execute(
            select(Document)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(
                Document.id == document_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")

        knowledge_base_id = doc.knowledge_base_id

        # Delete vector + sparse (BM25) index entries
        # （与幂等重跑共用同一清理逻辑，避免两处实现漂移）
        await self._purge_indexes(document_id)

        # Delete uploaded file
        for ext in settings.ALLOWED_EXTENSIONS:
            file_path = os.path.join(settings.UPLOAD_DIR, f"{document_id}{ext}")
            if os.path.exists(file_path):
                os.remove(file_path)
                break

        # Delete from database
        await db.delete(doc)
        await db.commit()

        # §5.4：知识库内容变了 → 该库的检索缓存必须失效
        if knowledge_base_id is not None:
            await self._invalidate_retrieval_cache(knowledge_base_id)

        logger.info(f"Document deleted: {doc.filename} ({document_id})")
        return {"message": "文档已删除", "document_id": document_id}

    async def get_document_status(self, document_id: str, db: AsyncSession, user_id: int) -> DocumentResponse:
        """Get document status (must belong to user)."""
        result = await db.execute(
            select(Document)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(
                Document.id == document_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        return DocumentResponse(**doc.to_dict())


# Singleton instance
document_service = DocumentService()