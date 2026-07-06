from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from loguru import logger
from ..core.config import settings
from ..models.document import Base
from ..models.user import User  # noqa: F401 - register User model for table creation
from ..models.knowledge_base import KnowledgeBase  # noqa: F401 - register KnowledgeBase model for table creation
from ..models.conversation import Conversation  # noqa: F401 - register Conversation model for table creation
from ..models.message import Message  # noqa: F401 - register Message model for table creation
from ..models.document import Document  # noqa: F401 - needed for migration
import os


# Create engine based on database URL
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=20,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Dependency: get async database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified successfully")

    # Migration: add knowledge_base_id to documents (for existing DBs)
    await _migrate_documents_add_kb_id()



async def close_db():
    """Dispose engine on shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed")


async def _migrate_documents_add_kb_id():
    """Migrate existing documents: add knowledge_base_id column and assign to default KB."""
    from sqlalchemy import text

    try:
        async with engine.begin() as conn:
            # 1. Add column if it doesn't exist (SQLite safe: try, ignore if exists)
            if settings.DATABASE_URL.startswith("sqlite"):
                try:
                    await conn.execute(text(
                        "ALTER TABLE documents ADD COLUMN knowledge_base_id INTEGER REFERENCES knowledge_bases(id)"
                    ))
                    logger.info("Migration: added knowledge_base_id column to documents")
                except Exception:
                    # Column already exists
                    pass
            else:
                # PostgreSQL: add column if not exists
                try:
                    await conn.execute(text(
                        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS knowledge_base_id INTEGER REFERENCES knowledge_bases(id)"
                    ))
                except Exception:
                    pass

            # 2. Assign existing documents with NULL kb_id to each user's default KB
            # For each user, find their default KB (first one created), then assign orphan docs
            await conn.execute(text("""
                UPDATE documents
                SET knowledge_base_id = (
                    SELECT kb.id FROM knowledge_bases kb
                    WHERE kb.user_id = (
                        SELECT u.id FROM users u
                        JOIN knowledge_bases kb2 ON kb2.user_id = u.id
                        -- This is a heuristic: assign to ANY user's default KB
                        -- Since old docs had no user separation, we use the first KB found
                        LIMIT 1
                    )
                    LIMIT 1
                )
                WHERE knowledge_base_id IS NULL
            """))
            logger.info("Migration: assigned existing documents to default knowledge bases")

    except Exception as e:
        logger.warning(f"Migration _migrate_documents_add_kb_id: {e}")
