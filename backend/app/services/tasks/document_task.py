"""
DocumentEmbeddingTask - 文档嵌入生成任务示例。

上传文件后提交此任务，Worker 异步生成 embedding。
"""
from typing import Any, Dict, Optional

from .base import TaskBase


class DocumentEmbeddingTask(TaskBase):
    """文档嵌入生成任务。"""

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