"""Numbering, saving and sending one run's events: saved in Postgres as the truth, then sent on Redis for whoever is listening."""

import logging
import time
from dataclasses import replace
from typing import Any

from redis.exceptions import RedisError

from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.features.runs.events import ASSISTANT_DELTA, RunEvent, cancel_channel, events_channel
from app.features.runs.repository import RunEventRepository


log = logging.getLogger(__name__)

DELTA_FLUSH_SECONDS = 1.0


async def send_live(run_id: int, event: RunEvent) -> None:

    """Send one numbered event on the run's Redis channel, logging instead of failing, since the saved copy is the truth."""

    try:
        await get_redis().publish(events_channel(run_id), event.to_wire())

    except RedisError:
        log.warning("could not send event %s of run %s live", event.seq, run_id, exc_info=True)


async def signal_cancel(run_id: int) -> None:

    """Ask whichever process runs this run to stop its task at once, logging instead of failing, since the saved status is the truth."""

    try:
        await get_redis().publish(cancel_channel(run_id), "1")

    except RedisError:
        log.warning("could not send the cancel of run %s", run_id, exc_info=True)


async def record_event(run_id: int, event: RunEvent) -> RunEvent:

    """Save and send one event for a run no worker is publishing for, such as a run ended outside its task."""

    async with SessionLocal() as session:

        events = RunEventRepository(session)

        seq = await events.last_seq(run_id) + 1

        await events.add(run_id, seq, event.name, event.data)

        await session.commit()

    numbered = replace(event, seq=seq)

    await send_live(run_id, numbered)

    return numbered


class RunPublisher:

    """Numbers one run's events, saves each in order with the reply's pieces grouped about once a second, and sends each live."""

    def __init__(self, run_id: int) -> None:

        """Start with no number yet and no unsaved pieces."""

        self.run_id = run_id
        self.seq = 0
        self.parts: list[dict[str, Any]] = []
        self.flushed_at = time.monotonic()

    async def open(self) -> "RunPublisher":

        """Carry on numbering after the run's last saved event, so a resumed run never reuses a number."""

        async with SessionLocal() as session:
            self.seq = await RunEventRepository(session).last_seq(self.run_id)

        return self

    async def emit(self, event: RunEvent) -> RunEvent:

        """Number the event, send a reply piece at once and save it with the next group, or save any other event first and then send it."""

        self.seq += 1

        numbered = replace(event, seq=self.seq)

        if event.name == ASSISTANT_DELTA:

            self.parts.append({"seq": self.seq, "text": event.data["text"]})

            await send_live(self.run_id, numbered)

            if time.monotonic() - self.flushed_at >= DELTA_FLUSH_SECONDS:
                await self.flush()

            return numbered

        await self.flush()

        async with SessionLocal() as session:

            await RunEventRepository(session).add(self.run_id, self.seq, event.name, event.data)

            await session.commit()

        await send_live(self.run_id, numbered)

        return numbered

    async def send_saved(self, event: RunEvent, seq: int) -> RunEvent:

        """Send an event the caller saved as seq in its own commit, and carry on numbering after it."""

        self.seq = seq

        numbered = replace(event, seq=seq)

        await send_live(self.run_id, numbered)

        return numbered

    async def flush(self) -> None:

        """Save the reply pieces not saved yet as one row, numbered as the last of them."""

        self.flushed_at = time.monotonic()

        if not self.parts:
            return

        parts, self.parts = self.parts, []

        async with SessionLocal() as session:

            await RunEventRepository(session).add(self.run_id, parts[-1]["seq"], ASSISTANT_DELTA, {"parts": parts})

            await session.commit()
