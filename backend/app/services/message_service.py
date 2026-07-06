from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.message import Message
from ..models.conversation import Conversation


async def _create_message(db: AsyncSession, conversation_id: int, role: str, content: str) -> dict:
    """Internal: save a message and update conversation.updated_at in a single transaction."""
    message = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(message)

    # Update conversation.updated_at via bulk UPDATE (no SELECT round-trip)
    try:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=datetime.now(timezone.utc))
        )
    except Exception:
        logger.exception(f"Failed to update conversation.updated_at for conversation_id={conversation_id}")

    await db.commit()
    await db.refresh(message)
    logger.info(f"Message saved: conversation_id={conversation_id}, message_id={message.id}, role={role}")
    return message.to_dict()


async def create_user_message(db: AsyncSession, conversation_id: int, content: str) -> dict:
    """Save a user message to the Message table."""
    return await _create_message(db, conversation_id, "user", content)


async def create_assistant_message(db: AsyncSession, conversation_id: int, content: str) -> dict:
    """Save an assistant message to the Message table."""
    return await _create_message(db, conversation_id, "assistant", content)