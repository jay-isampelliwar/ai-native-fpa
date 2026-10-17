"""Database reads and writes for memory items and their history."""

from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import MemoryActorType, MemoryEventType, MemoryStatus, MessageRole
from app.db.models import Conversation, MemoryEvent, MemoryItem, Message
from app.features.memory.schemas import MemoryCandidate, MemorySource


CHAT_ROLES = (MessageRole.user, MessageRole.assistant)


class MemoryRepository:

    """All memory queries for one event, sharing one session so the memories and their history commit together."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the worker's session, so every write lands in the same commit."""

        self.session = session

    async def already_processed(self, outbox_event_id: int) -> bool:

        """Return True if this outbox event already wrote memory history, so a redelivery can be skipped."""

        query = select(exists().where(MemoryEvent.outbox_event_id == outbox_event_id))

        return bool(await self.session.scalar(query))

    async def run_messages(
        self,
        run_id: int,
        user_id: int,
        ) -> list[Message]:

        """Return the run's user and assistant messages in order, only if the run's chat belongs to this user."""

        query = (
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.run_id == run_id,
                Message.role.in_(CHAT_ROLES),
                Conversation.user_id == user_id,
                )
            .order_by(Message.sequence_number)
            )

        return list(await self.session.scalars(query))

    async def active_memories(self, user_id: int) -> list[MemoryItem]:

        """Return the user's active memories, oldest first, so the extractor can reuse their keys."""

        query = (
            select(MemoryItem)
            .where(MemoryItem.user_id == user_id, MemoryItem.status == MemoryStatus.active)
            .order_by(MemoryItem.id)
            )

        return list(await self.session.scalars(query))

    async def save_candidate(
        self,
        candidate: MemoryCandidate,
        source: MemorySource,
        ) -> MemoryItem:

        """Save one memory with a created history row, first superseding any active memory with the same key."""

        provenance = self.provenance(source, candidate.source_message_id)

        current = await self.active_with_key(source.user_id, candidate)

        if current is not None:

            current.status = MemoryStatus.superseded

            await self.session.flush()

            self.add_history(current, MemoryEventType.superseded, provenance, old_content=current.content)

        item = MemoryItem(
            user_id=source.user_id,
            memory_type=candidate.memory_type,
            namespace=candidate.namespace,
            memory_key=candidate.memory_key,
            content=candidate.content,
            confidence=candidate.confidence,
            confirmed_by_user=candidate.confirmed_by_user,
            status=candidate.status,
            source_message_id=candidate.source_message_id,
            source_conversation_id=source.conversation_id,
            source_run_id=source.run_id,
            )

        self.session.add(item)

        await self.session.flush()

        self.add_history(item, MemoryEventType.created, provenance, new_content=item.content)

        await self.session.flush()

        return item

    async def active_with_key(
        self,
        user_id: int,
        candidate: MemoryCandidate,
        ) -> MemoryItem | None:

        """Lock and return the user's active memory with the candidate's namespace and key, if the candidate would replace it."""

        if candidate.memory_key is None or candidate.status != MemoryStatus.active:
            return None

        query = (
            select(MemoryItem)
            .where(
                MemoryItem.user_id == user_id,
                MemoryItem.namespace == candidate.namespace,
                MemoryItem.memory_key == candidate.memory_key,
                MemoryItem.status == MemoryStatus.active,
                )
            .with_for_update()
            )

        return await self.session.scalar(query)

    def add_history(
        self,
        item: MemoryItem,
        event_type: MemoryEventType,
        provenance: dict[str, Any],
        old_content: dict[str, Any] | None = None,
        new_content: dict[str, Any] | None = None,
        ) -> None:

        """Add one agent-made history row for a memory, without flushing."""

        self.session.add(
            MemoryEvent(
                memory_id=item.id,
                user_id=item.user_id,
                event_type=event_type,
                old_content=old_content,
                new_content=new_content,
                actor_type=MemoryActorType.agent,
                **provenance,
                )
            )

    @staticmethod
    def provenance(
        source: MemorySource,
        message_id: int | None,
        ) -> dict[str, Any]:

        """The source columns every history row from this event carries."""

        return {
            "source_message_id": message_id,
            "source_conversation_id": source.conversation_id,
            "source_run_id": source.run_id,
            "outbox_event_id": source.outbox_event_id,
            }
