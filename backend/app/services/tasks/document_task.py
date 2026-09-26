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
        """执行完整入库流程，并维护 Document 状态。"""
        from ...models.document import DocumentStatus
        from ..knowledge.context import KnowledgePipelineContext
        from ..knowledge.pipeline import KnowledgePipeline

        await self._update_status(DocumentStatus.PROCESSING.value)

        try:
            pipeline = KnowledgePipeline()
            context = KnowledgePipelineContext(
                file_path=self.file_path,
                document_id=self.document_id,
                filename=self.filename,
                knowledge_base_id=self.knowledge_base_id,
            )
            chunk_count = await pipeline.process_document(context)
        except Exception as exc:
            logger.error(f"后台文档处理失败: {self.filename} - {exc}")
            await self._update_status(
                DocumentStatus.FAILED.value, error_message=str(exc)[:500]
            )
            raise

        await self._update_status(
            DocumentStatus.COMPLETED.value,
            chunk_count=chunk_count,
            error_message="",
        )
        return {
            "document_id": self.document_id,
            "knowledge_base_id": self.knowledge_base_id,
            "chunks_count": chunk_count,
            "status": DocumentStatus.COMPLETED.value,
        }

    async def _update_status(
        self,
        status: str,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """更新 Document 行状态（独立 session，与请求事务解耦）。"""
        from ...models.document import Document
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
            await session.commit()

        logger.info(f"文档状态更新: {self.document_id} → {status}")


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