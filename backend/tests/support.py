"""Shared helpers that create temp users and runs on the real database and remove everything they made."""

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.models import AgentRun, Conversation, MemoryEvent, MemoryItem, Message, OutboxEvent, User
from app.db.session import SessionLocal
from app.features.runs.repository import RunRepository


USER_TEXT = "I avoid tobacco stocks"


@dataclass
class SeededRun:

    """The ids of a temp user, their conversation, one queued run and its two messages."""

    user_id: int
    conversation_id: int
    run_id: int
    user_message_id: int
    assistant_message_id: int


async def create_user() -> int:

    """Create a temp user with a unique email and return its id."""

    async with SessionLocal() as session:

        user = User(name="Test User", email=f"test-{uuid4().hex}@example.com")

        session.add(user)

        await session.commit()

        return user.id


async def seed_run(user_id: int) -> SeededRun:

    """Create a conversation with one queued run, its user message and an empty assistant message."""

    async with SessionLocal() as session:

        repository = RunRepository(session)

        conversation = await repository.create_conversation(user_id, "Test chat")

        run, user_message, assistant_message = await repository.create_run_with_messages(
            conversation.id,
            uuid4().hex,
            USER_TEXT,
            )

        await session.commit()

        return SeededRun(user_id, conversation.id, run.id, user_message.id, assistant_message.id)


async def delete_user_data(user_id: int) -> None:

    """Delete a temp user and every memory, outbox event, message, run and conversation they own."""

    async with SessionLocal() as session:

        conversation_ids = select(Conversation.id).where(Conversation.user_id == user_id)

        await session.execute(delete(MemoryEvent).where(MemoryEvent.user_id == user_id))
        await session.execute(delete(MemoryItem).where(MemoryItem.user_id == user_id))
        await session.execute(delete(OutboxEvent).where(OutboxEvent.user_id == user_id))
        await session.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
        await session.execute(delete(AgentRun).where(AgentRun.conversation_id.in_(conversation_ids)))
        await session.execute(delete(Conversation).where(Conversation.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))

        await session.commit()
