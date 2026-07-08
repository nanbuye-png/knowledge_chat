from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.conversation import Conversation


async def create_conversation(db: AsyncSession, knowledge_base_id: int) -> dict:
    """Create a new conversation under the given knowledge base."""
    conversation = Conversation(knowledge_base_id=knowledge_base_id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation.to_dict()


async def get_conversations(db: AsyncSession, knowledge_base_id: int) -> list[dict]:
    """List all conversations under the given knowledge base, ordered by updated_at DESC."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.knowledge_base_id == knowledge_base_id)
        .order_by(Conversation.updated_at.desc())
    )
    conversations = result.scalars().all()
    return [conv.to_dict() for conv in conversations]


async def update_conversation_title(db: AsyncSession, conversation_id: int, title: str) -> dict:
    """Update a conversation's title."""
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


async def delete_conversation(db: AsyncSession, conversation_id: int) -> bool:
    """Delete a conversation by id. Returns True if deleted, False if not found."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return False
    await db.delete(conversation)
    await db.commit()
    return True


async def rename_conversation(db: AsyncSession, conversation_id: int, title: str) -> dict:
    """Rename a conversation. Strips whitespace, enforces max 100 chars, cannot be empty."""
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
