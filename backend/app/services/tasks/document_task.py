"""
DocumentEmbeddingTask - 文档嵌入生成任务示例。

上传文件后提交此任务，Worker 异步生成 embedding。
"""
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select

from .base import TaskBase


class DocumentProcessingTask(TaskBase):
    """后台处理一篇已上传的文档（P0-4）。

    把一个已落盘的文件走完：解析 → 切分 → 向量化 → 向量库/稀疏索引，
    并同步维护 ``Document.status``：

        PENDING → PROCESSING → COMPLETED
                            ↘ FAILED（记录 error_message）

    任务由 :class:`~app.services.tasks.local_worker.LocalWorker` 在**独立线程**
    中执行，因此不依赖上传请求的生命周期。
    """

    def __init__(
        self,
        document_id: str,
        file_path: str,
        filename: str,
        knowledge_base_id: int,
        task_id: Optional[str] = None,
    ):
        super().__init__(task_id)
        self.document_id = document_id
        self.file_path = file_path
        self.filename = filename
        self.knowledge_base_id = knowledge_base_id

    async def run(self) -> Dict[str, Any]:
        """执行完整入库流程，并维护 Document 状态。

        失败处理（Phase 3 §5.2）
        -----------------------
        只有当异常属于**可重试**类别（网络 / 超时 / 429 / 5xx）时才整篇重试；
        次数与退避由 ``TASK_RETRY_*`` 配置驱动，重试次数写入
        ``Document.retry_count``。不可重试的错误（如"文档内容为空"）立即失败，
        不做无意义重试；最终失败仍向上抛出，由 Worker 记录任务状态。
        """
        from ...core.retry import retry_async, task_policy
        from ...models.document import DocumentStatus

        await self._update_status(DocumentStatus.PROCESSING.value, retry_count=0)

        retries: list[int] = []

        async def _on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            retries.append(attempt)
            logger.warning(
                f"文档处理失败，准备第 {attempt} 次重试（{self.filename}，"
                f"{delay:.1f}s 后）: {type(exc).__name__}: {exc}"
            )
            await self._update_status(
                DocumentStatus.PROCESSING.value,
                error_message=str(exc)[:500],
                retry_count=attempt,
            )

        try:
            chunk_count = await retry_async(
                self._process_once,
                policy=task_policy(),
                operation=f"document:{self.filename}",
                on_retry=_on_retry,
            )
        except Exception as exc:
            logger.error(f"后台文档处理失败: {self.filename} - {exc}")
            await self._update_status(
                DocumentStatus.FAILED.value,
                error_message=str(exc)[:500],
                retry_count=len(retries),
            )
            raise

        await self._update_status(
            DocumentStatus.COMPLETED.value,
            chunk_count=chunk_count,
            error_message="",
            retry_count=len(retries),
        )
        return {
            "document_id": self.document_id,
            "knowledge_base_id": self.knowledge_base_id,
            "chunks_count": chunk_count,
            "status": DocumentStatus.COMPLETED.value,
            "retry_count": len(retries),
        }

    async def _process_once(self) -> int:
        """跑一次完整入库流程（解析 → 切分 → 向量化 → 落库）。"""
        from ..knowledge.context import KnowledgePipelineContext
        from ..knowledge.pipeline import KnowledgePipeline

        pipeline = KnowledgePipeline()
        context = KnowledgePipelineContext(
            file_path=self.file_path,
            document_id=self.document_id,
            filename=self.filename,
            knowledge_base_id=self.knowledge_base_id,
        )
        return await pipeline.process_document(context)

    async def _update_status(
        self,
        status: str,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None,
        retry_count: Optional[int] = None,
    ) -> None:
        """更新 Document 行状态（独立 session，与请求事务解耦）。"""
        from ...models.document import Document, DocumentStatus
        from ...storage.database import async_session

        async with async_session() as session:
            result = await session.execute(
                select(Document).where(Document.id == self.document_id)
            )
            doc = result.scalar_one_or_none()
            if doc is None:
                logger.warning(
                    f"更新文档状态失败：文档不存在（document_id={self.document_id}）"
                )
                return

            doc.status = status
            if chunk_count is not None:
                doc.chunk_count = chunk_count
            if error_message is not None:
                doc.error_message = error_message or None
            if retry_count is not None:
                doc.retry_count = retry_count
            await session.commit()

        logger.info(
            f"文档状态更新: {self.document_id} → {status}"
            + (f"（retry_count={retry_count}）" if retry_count else "")
        )
        # §5.6：状态流转进指标 —— "有多少文档卡在 pending/failed" 必须可被查询
        from ...services.metrics import track_document_status

        track_document_status(status if isinstance(status, str) else str(status))

        # §5.4：文档内容变化（完成或失败都可能已写入部分向量）→ 检索缓存失效
        if status in (DocumentStatus.COMPLETED.value, DocumentStatus.FAILED.value):
            try:
                from ...services.cache.retrieval_cache import RetrievalCache

                await RetrievalCache().invalidate_knowledge_base(self.knowledge_base_id)
            except Exception as exc:  # noqa: BLE001 - 缓存失效失败不能影响入库结果
                logger.warning(f"检索缓存失效失败（kb={self.knowledge_base_id}）: {exc}")


class DocumentEmbeddingTask(TaskBase):
    """**演示桩**（不参与上传链路）。

    历史上它是"文档嵌入任务"的占位实现，``run()`` 返回硬编码分块数，
    容易让人误以为入库已经异步化；真正的入库路径为
    :class:`DocumentProcessingTask`。
    """

    def __init__(
        self,
        document_id: str,
        knowledge_base_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ):
        super().__init__(task_id)
        self.document_id = document_id
        self.knowledge_base_id = knowledge_base_id
        self.content = content
        self.metadata = metadata or {}

    async def run(self) -> Dict[str, Any]:
        """执行嵌入生成。

        实际实现将调用 Embedding 服务，此处返回占位结果。
        """
        # TODO: 调用 EmbeddingService 生成向量
        # embeddings = await EmbeddingService.embed(self.content)

        result = {
            "document_id": self.document_id,
            "knowledge_base_id": self.knowledge_base_id,
            "chunks_count": len(self.content) // 500 + 1,  # 按 500 字分块
            "status": "embedded",
        }
        return result