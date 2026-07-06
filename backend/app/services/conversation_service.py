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
