"""
Knowledge Debug API — for debugging retrieval quality.

Provides temporary endpoints to inspect what chunks are returned
for a given query, to help identify content loss in the pipeline.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from loguru import logger

from ..storage.vector_store import vector_store
from ..services.embedding.factory import EmbeddingProviderFactory
from ..core.config import settings
from ..auth.deps import get_current_user
from ..models.user import User

router = APIRouter(prefix="/api/knowledge/debug", tags=["知识库调试"])


class RetrievalDebugResult(BaseModel):
    score: float
    content: str
    document_id: str | None = None
    filename: str | None = None


class RetrievalDebugResponse(BaseModel):
    query: str
    results: list[RetrievalDebugResult]


@router.get(
    "/retrieval",
    response_model=RetrievalDebugResponse,
    summary="调试：查看检索到的原始 Chunk 内容",
)
async def debug_retrieval(
    query: str = Query(..., description="搜索查询"),
    knowledge_base_id: int = Query(..., description="知识库 ID"),
    top_k: int = Query(5, ge=1, le=20, description="返回 top K 个 chunk"),
    current_user: User = Depends(get_current_user),
):
    """返回指定查询在向量库中的原始检索结果，用于调试文档内容是否完整。"""
    if not vector_store.collection:
        raise HTTPException(status_code=503, detail="向量存储未初始化")

    # 生成查询向量
    model_name = settings.EMBEDDING_MODEL
    provider_name = model_name.split("/")[-1].split("-")[0] if "/" in model_name else "bge"
    provider = EmbeddingProviderFactory.create(
        provider_name=provider_name,
        model_name=model_name,
        embedding_dim=settings.EMBEDDING_DIM,
    )
    await provider.initialize()

    try:
        query_embedding = await provider.embed_query(query)

        # 查询 Chroma
        where_filter = {"knowledge_base_id": str(knowledge_base_id)}
        results = vector_store.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
        )

        items: list[RetrievalDebugResult] = []
        if results and results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                content = results["documents"][0][i] if results["documents"] else ""
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                score = results["distances"][0][i] if results["distances"] else 0.0

                items.append(RetrievalDebugResult(
                    score=round(score, 4),
                    content=content,
                    document_id=doc_id,
                    filename=metadata.get("filename"),
                ))

        logger.info(f"Debug retrieval: query='{query}', kb={knowledge_base_id}, hits={len(items)}")
        return RetrievalDebugResponse(query=query, results=items)

    finally:
        await provider.close()