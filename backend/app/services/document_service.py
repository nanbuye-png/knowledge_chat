import os
import uuid
import shutil
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from fastapi import UploadFile, HTTPException

from ..core.config import settings
from ..models.document import Document, DocumentStatus
from ..models.knowledge_base import KnowledgeBase
from ..schemas.document import DocumentResponse, DocumentListResponse
from ..utils.file_parser import parse_file
from ..utils.text_chunker import chunk_text
from ..services.embedding_service import embedding_service
from ..storage.vector_store import vector_store


class DocumentService:
    """Service for document management."""

    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md", ".txt"}

    async def upload_document(self, file: UploadFile, db: AsyncSession, user_id: int, knowledge_base_id: int) -> Document:
        """Upload and process a document.

        Args:
            file: The uploaded file.
            db: Database session.
            user_id: The current user's ID.
            knowledge_base_id: The target knowledge base ID (must belong to the user).
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

        # Save file
        file_ext = os.path.splitext(file.filename)[1].lower()
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        file_size = len(content)

        # Create document record
        doc = Document(
            id=file_id,
            filename=file.filename,
            file_size=file_size,
            file_type=file_ext,
            status=DocumentStatus.PROCESSING.value,
            knowledge_base_id=knowledge_base_id,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # Process asynchronously
        try:
            await self._process_document(file_path, doc)
        except Exception as e:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = str(e)[:500]
            await db.commit()
            logger.error(f"Document processing failed: {file.filename} - {e}")

        return doc

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

    async def _process_document(self, file_path: str, doc: Document):
        """Process document: parse, chunk, embed, and store."""
        from ..storage.database import async_session

        try:
            # 1. Parse
            logger.info(f"Parsing document: {doc.filename}")
            text = parse_file(file_path)
            if not text.strip():
                raise ValueError("文档内容为空，无法处理")

            # 2. Chunk
            logger.info(f"Chunking text: {len(text)} chars")
            chunks = chunk_text(text)
            if not chunks:
                raise ValueError("文档切块后内容为空")

            # 3. Embed
            logger.info(f"Generating embeddings for {len(chunks)} chunks")
            embeddings = await embedding_service.embed_texts(chunks)

            # 4. Store in vector DB (with knowledge_base_id and user_id for isolation)
            logger.info(f"Storing {len(chunks)} chunks in vector store (kb={doc.knowledge_base_id})")
            # Look up user_id from KB
            async with async_session() as session:
                kb_result = await session.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == doc.knowledge_base_id)
                )
                kb = kb_result.scalar_one_or_none()
                user_id = kb.user_id if kb else None

            await vector_store.add_document_chunks(
                document_id=doc.id,
                filename=doc.filename,
                chunks=chunks,
                embeddings=embeddings,
                knowledge_base_id=doc.knowledge_base_id,
                user_id=user_id,
            )

            # 5. Update document status
            async with async_session() as session:
                result = await session.execute(select(Document).where(Document.id == doc.id))
                db_doc = result.scalar_one_or_none()
                if db_doc:
                    db_doc.status = DocumentStatus.COMPLETED.value
                    db_doc.chunk_count = len(chunks)
                    await session.commit()

            logger.info(f"Document processed successfully: {doc.filename} ({len(chunks)} chunks)")

        except Exception as e:
            # Update status to failed
            async with async_session() as session:
                result = await session.execute(select(Document).where(Document.id == doc.id))
                db_doc = result.scalar_one_or_none()
                if db_doc:
                    db_doc.status = DocumentStatus.FAILED.value
                    db_doc.error_message = str(e)[:500]
                    await session.commit()
            raise

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

        # Delete from vector store
        try:
            await vector_store.delete_document(document_id)
        except Exception as e:
            logger.warning(f"Vector store deletion warning: {e}")

        # Delete uploaded file
        for ext in settings.ALLOWED_EXTENSIONS:
            file_path = os.path.join(settings.UPLOAD_DIR, f"{document_id}{ext}")
            if os.path.exists(file_path):
                os.remove(file_path)
                break

        # Delete from database
        await db.delete(doc)
        await db.commit()

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