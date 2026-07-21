from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.conversation import Conversation
from ..models.knowledge_base import KnowledgeBase


async def _verify_kb_ownership(db: AsyncSession, knowledge_base_id: int, user_id: int) -> KnowledgeBase:
    """Verify the knowledge base belongs to the user. Raises ValueError if not."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.user_id == user_id,
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise ValueError("Knowledge base not found or access denied")
    return kb


async def _verify_conversation_ownership(db: AsyncSession, conversation_id: int, user_id: int) -> Conversation:
    """Verify the conversation belongs to the user. Raises ValueError."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise ValueError("Conversation not found or access denied")
    return conv


async def create_conversation(db: AsyncSession, knowledge_base_id: int | None, user_id: int) -> dict:
    """Create a new conversation.
    
    If knowledge_base_id is provided, it must belong to the user.
    If knowledge_base_id is None, creates a general chat conversation (no KB).
    """
    if knowledge_base_id is not None:
        await _verify_kb_ownership(db, knowledge_base_id, user_id)
    conversation = Conversation(
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation.to_dict()


async def get_conversations(db: AsyncSession, knowledge_base_id: int | None, user_id: int) -> list[dict]:
    """List all conversations.
    
    If knowledge_base_id is provided, filter by that KB (must belong to user).
    If knowledge_base_id is None, return all conversations for the user.
    Ordered by updated_at DESC.
    """
    if knowledge_base_id is not None:
        await _verify_kb_ownership(db, knowledge_base_id, user_id)
        stmt = (
            select(Conversation)
            .where(
                Conversation.knowledge_base_id == knowledge_base_id,
                Conversation.user_id == user_id,
            )
            .order_by(Conversation.updated_at.desc())
        )
    else:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
    result = await db.execute(stmt)
    conversations = result.scalars().all()
    return [conv.to_dict() for conv in conversations]


async def update_conversation_title(db: AsyncSession, conversation_id: int, title: str) -> dict:
    """Update a conversation's title (no user check, internal helper)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise ValueError(f"Conversation with id {conversation_id} not found")
    conversation.title = title
    await db.commit()
    await db.refresh(conversation)
    return conversation.to_dict()


async def delete_conversation(db: AsyncSession, conversation_id: int, user_id: int) -> bool:
    """Delete a conversation by id (must belong to user). Returns True if deleted."""
    await _verify_conversation_ownership(db, conversation_id, user_id)
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return False
    await db.delete(conversation)
    await db.commit()
    return True


async def rename_conversation(db: AsyncSession, conversation_id: int, title: str, user_id: int) -> dict:
    """Rename a conversation (must belong to user). Strips whitespace, max 100 chars."""
    await _verify_conversation_ownership(db, conversation_id, user_id)
    title = title.strip()
    if not title:
        raise ValueError("Title cannot be empty")
    if len(title) > 100:
        title = title[:100]
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise ValueError(f"Conversation with id {conversation_id} not found")
    conversation.title = title
    await db.commit()
    await db.refresh(conversation)
    return conversation.to_dict()