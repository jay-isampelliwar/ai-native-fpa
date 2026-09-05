"""Reading and appending the chat transcript, the one surface in this service that also deletes.

Appending a turn is deliberately one call that does four things: it creates the conversation if this
is its first message, works out the next position, writes the row, and moves the conversation's
counters. Splitting those apart would let a caller write a message into a session that does not
exist, or leave ``last_message_at`` behind after a turn - and a chat list sorted by a stale timestamp
puts the conversation someone just had at the bottom.

All four happen in one ``session_scope``, so a turn is either recorded completely or not at all. This
is not the audit trail's rule, where a record must survive the failure it describes; a half written
transcript has no value to preserve.

``position`` is read as ``max + 1`` inside the same transaction rather than taken from a sequence.
Two concurrent writes to one conversation would collide on the unique constraint, which is the
correct outcome: a person does not hold two turns of the same conversation at once, and a collision
means something is wrong that a silently renumbered row would hide.

The title comes from the first user message, trimmed to fit. It is set once and never rewritten,
because a list whose entries change name as a conversation goes on is one nobody can navigate by
memory.

Every read is scoped by ``user_id`` and a conversation belonging to somebody else is reported as
missing, matching every other surface here. Ownership is checked against the message table's own
column rather than through a join, which is what its index exists for.

Deletion is offered because a chat someone chose to discard is theirs to discard. It cascades to the
messages and stops there - nothing financial, and no audit record, is reachable from it.
"""

from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.models.orm.conversations import TITLE_LENGTH, ConversationMessageRow, ConversationRow


class ConversationsRepository:

    """Appends turns to a conversation and reads back the sessions and transcripts of one user."""

    async def append(
        self,
        user_id: int,
        conversation_id: str,
        role: str,
        text: str,
        blocks: list | None = None,
        skill_name: str | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        evidence_ids: list[str] | None = None,
        calculator_versions: list[str] | None = None,
        ) -> ConversationMessageRow:

        """Record one turn, creating the conversation on its first message and moving its counters."""

        async with session_scope() as session:

            conversation = await self._ensure(session, user_id, conversation_id, role, text)

            position = await session.scalar(
                select(func.coalesce(func.max(ConversationMessageRow.position), 0) + 1).where(
                    ConversationMessageRow.conversation_id == conversation_id
                )
            )

            row = ConversationMessageRow(
                id=f"msg_{uuid4().hex[:12]}",
                conversation_id=conversation_id,
                user_id=user_id,
                position=position or 1,
                role=role,
                text=text,
                blocks=blocks or [],
                skill_name=skill_name,
                status=status,
                correlation_id=correlation_id,
                evidence_ids=evidence_ids or [],
                calculator_versions=calculator_versions or [],
            )

            session.add(row)

            conversation.message_count = (conversation.message_count or 0) + 1
            conversation.last_message_at = func.now()

            return row

    async def sessions(self, user_id: int, limit: int = 50) -> list[ConversationRow]:

        """List one user's conversations, most recently spoken to first, for the history panel."""

        async with session_scope() as session:

            rows = await session.scalars(
                select(ConversationRow)
                .where(ConversationRow.user_id == user_id)
                .order_by(ConversationRow.last_message_at.desc())
                .limit(limit)
            )

            return list(rows)

    async def find(self, user_id: int, conversation_id: str) -> ConversationRow | None:

        """Fetch one conversation this user owns, reporting one they do not own as missing."""

        async with session_scope() as session:

            return await session.scalar(
                select(ConversationRow).where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.user_id == user_id,
                )
            )

    async def transcript(
        self,
        user_id: int,
        conversation_id: str,
        limit: int = 500,
        ) -> list[ConversationMessageRow]:

        """Read one conversation's turns in the order they happened, scoped to their owner."""

        async with session_scope() as session:

            rows = await session.scalars(
                select(ConversationMessageRow)
                .where(
                    ConversationMessageRow.conversation_id == conversation_id,
                    ConversationMessageRow.user_id == user_id,
                )
                .order_by(ConversationMessageRow.position)
                .limit(limit)
            )

            return list(rows)

    async def discard(self, user_id: int, conversation_id: str) -> bool:

        """Delete one conversation and its messages, reporting whether there was one to delete."""

        async with session_scope() as session:

            outcome = await session.execute(
                delete(ConversationRow).where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.user_id == user_id,
                )
            )

            return outcome.rowcount > 0

    async def _ensure(
        self,
        session: AsyncSession,
        user_id: int,
        conversation_id: str,
        role: str,
        text: str,
        ) -> ConversationRow:

        """Return the conversation this turn belongs to, creating it if this is its first message."""

        conversation = await session.get(ConversationRow, conversation_id)

        if conversation is not None:
            return conversation

        conversation = ConversationRow(
            id=conversation_id,
            user_id=user_id,
            title=title_from(text) if role == "user" else None,
            message_count=0,
        )

        session.add(conversation)

        await session.flush()

        return conversation


def title_from(text: str) -> str:

    """Name a conversation after the first thing the person said, trimmed to fit the column."""

    cleaned = " ".join(text.split())

    if len(cleaned) <= TITLE_LENGTH:
        return cleaned

    return cleaned[: TITLE_LENGTH - 1].rstrip() + "…"


conversations_repository = ConversationsRepository()
