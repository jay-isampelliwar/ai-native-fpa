"""Database reads and writes for outbox events."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OutboxEventType, OutboxStatus
from app.db.models import OutboxEvent


EVENT_VERSION = 1

RUN_AGGREGATE = "agent_run"


class OutboxRepository:

    """All outbox queries for one unit of work, sharing the caller's session so events commit with their cause."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the caller's session, so the event lands in the same commit as the change that caused it."""

        self.session = session

    async def add_event(
        self,
        event_type: OutboxEventType,
        aggregate_type: str,
        aggregate_id: int,
        user_id: int,
        payload: dict[str, Any],
        ) -> int | None:

        """Add a pending event without committing, and return its id, or None if this event already exists."""

        query = (
            insert(OutboxEvent)
            .values(
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                user_id=user_id,
                payload={"event_version": EVENT_VERSION, **payload},
                )
            .on_conflict_do_nothing(constraint="uq_outbox_events_event_aggregate")
            .returning(OutboxEvent.id)
            )

        return await self.session.scalar(query)

    async def add_memory_extract(
        self,
        run_id: int,
        conversation_id: int,
        user_id: int,
        ) -> int | None:

        """Ask the memory worker to read a completed run, keyed on the run so it is asked only once."""

        return await self.add_event(
            OutboxEventType.memory_extract_requested,
            RUN_AGGREGATE,
            run_id,
            user_id,
            {"user_id": user_id, "conversation_id": conversation_id, "run_id": run_id},
            )

    async def claim_pending(self, limit: int) -> list[OutboxEvent]:

        """Lock up to limit due pending events, oldest first, skipping rows another publisher already holds."""

        query = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.pending, OutboxEvent.available_at <= func.now())
            .order_by(OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
            )

        return list(await self.session.scalars(query))

    def mark_published(self, event: OutboxEvent) -> None:

        """Record that the event reached Redis, without committing."""

        event.status = OutboxStatus.published
        event.processed_at = func.now()
        event.last_error = None

    def mark_retry(
        self,
        event: OutboxEvent,
        error: str,
        retry_limit: int,
        ) -> None:

        """Count a failed publish and wait 2^attempts seconds before the next try, or dead letter it at the limit."""

        event.attempts += 1
        event.last_error = error[:1000]

        if event.attempts >= retry_limit:

            event.status = OutboxStatus.dead_letter

            return

        event.available_at = datetime.now(UTC) + timedelta(seconds=2 ** event.attempts)
