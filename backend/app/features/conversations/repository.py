"""Database reads for the history list and for opening one conversation."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Row, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ACTIVE_RUN_STATUSES, ConversationStatus, MessageRole
from app.db.models import AgentRun, Conversation, Message


SHOWN_ROLES = (MessageRole.user, MessageRole.assistant)


class ConversationRepository:

    """All conversation queries for one request, sharing that request's session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session this request opened, so every method talks through it."""

        self.session = session

    async def list_for_user(self, user_id: int, limit: int) -> Sequence[Row[Any]]:

        """Return the user's active chats that have messages, newest activity first, each with its first user message."""

        first_message = (
            select(Message.content["text"].astext)
            .where(Message.conversation_id == Conversation.id, Message.role == MessageRole.user)
            .order_by(Message.sequence_number)
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
            )

        query = (
            select(Conversation, first_message.label("first_message"))
            .where(
                Conversation.user_id == user_id,
                Conversation.status == ConversationStatus.active,
                Conversation.current_sequence > 0,
                )
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit)
            )

        result = await self.session.execute(query)

        return result.all()

    async def get_for_user(self, conversation_id: int, user_id: int) -> Conversation | None:

        """Return the conversation only when it exists, is not deleted and belongs to this user."""

        query = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.status != ConversationStatus.deleted,
            )

        return await self.session.scalar(query)

    async def rename(self, conversation: Conversation, title: str) -> None:

        """Set the conversation's title without touching updated_at, so the history order stays the same."""

        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation.id)
            .values(title=title, updated_at=Conversation.updated_at)
            )

        await self.session.refresh(conversation)

    async def soft_delete(self, conversation: Conversation) -> None:

        """Mark the conversation deleted and stamp when, keeping every row in the database."""

        conversation.status = ConversationStatus.deleted
        conversation.deleted_at = func.now()

        await self.session.flush()

    async def list_messages(self, conversation_id: int) -> Sequence[Message]:

        """Return the conversation's user and assistant messages in the order they were written."""

        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.role.in_(SHOWN_ROLES))
            .order_by(Message.sequence_number)
            )

        result = await self.session.scalars(query)

        return result.all()

    async def get_active_run(self, conversation_id: int) -> AgentRun | None:

        """Return the run still queued, running or cancelling in this conversation, if there is one."""

        query = select(AgentRun).where(
            AgentRun.conversation_id == conversation_id,
            AgentRun.status.in_(ACTIVE_RUN_STATUSES),
            )

        return await self.session.scalar(query)
