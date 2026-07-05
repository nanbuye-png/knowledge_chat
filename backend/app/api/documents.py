from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..storage.database import get_db
from ..schemas.document import (
    DocumentResponse, DocumentListResponse,
    UploadResponse, DeleteResponse,
)
from ..services.document_service import document_service
from ..core.config import settings
from ..auth.deps import get_current_user
from ..models.user import User

router = APIRouter(prefix="/api/documents", tags=["文档管理"])


@router.post("/upload", response_model=UploadResponse, summary="上传文档")
async def upload_document(
    file: UploadFile = File(...),
    knowledge_base_id: int = Query(..., description="目标知识库 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传文档文件到指定知识库，支持 PDF、DOCX、MD、TXT 格式。"""
    logger.info(f"Received upload request: {file.filename} -> kb={knowledge_base_id} by user={current_user.username}")

    # Validate file extension
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if f".{ext}" not in settings.ALLOWED_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_EXTENSIONS)
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 '.{ext}'。支持的类型: {allowed}"
        )

    try:
        doc = await document_service.upload_document(file, db, user_id=current_user.id, knowledge_base_id=knowledge_base_id)
        return UploadResponse(
            message="文档上传成功，正在处理中",
            document_id=doc.id,
            filename=doc.filename,
            status=doc.status,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("", response_model=DocumentListResponse, summary="获取文档列表")
async def list_documents(
    knowledge_base_id: int = Query(..., description="知识库 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定知识库的文档列表。"""
    try:
        result = await document_service.get_documents(db, knowledge_base_id=knowledge_base_id)
        return result
    except Exception as e:
        logger.error(f"List documents failed: {e}")
        raise HTTPException(status_code=500, detail="获取文档列表失败")


@router.delete("/{document_id}", response_model=DeleteResponse, summary="删除文档")
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除指定文档及其向量数据。"""
    try:
        result = await document_service.delete_document(document_id, db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document failed: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/{document_id}/status", response_model=DocumentResponse, summary="获取文档状态")
async def get_document_status(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个文档的处理状态。"""
    try:
        return await document_service.get_document_status(document_id, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get document status failed: {e}")
        raise HTTPException(status_code=500, detail="获取文档状态失败")