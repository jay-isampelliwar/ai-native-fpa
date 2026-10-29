"""Following one run's events for a listener on any API process: catch up from Postgres, then carry on live from Redis, with no gap and no repeat."""

import asyncio
import logging
from collections.abc import AsyncIterator

from app.core.redis import get_redis
from app.db.enums import RunStatus
from app.db.models import RunEventRecord
from app.db.session import SessionLocal
from app.features.approvals.repository import ApprovalRepository
from app.features.runs.events import (
    APPROVAL_REQUIRED,
    ASSISTANT_DELTA,
    ASSISTANT_SNAPSHOT,
    FINAL_EVENT_FOR_STATUS,
    FINAL_EVENTS,
    STREAM_END_EVENTS,
    RunEvent,
    events_channel,
    )
from app.features.runs.repository import RunEventRepository, RunRepository
from app.features.runs.worker import approval_event


log = logging.getLogger(__name__)

KEEPALIVE = ": keepalive\n\n"

POLL_SECONDS = 1.0

KEEPALIVE_EVERY_POLLS = 15

STATUS_CHECK_EVERY_POLLS = 15

GAP_WAIT_SECONDS = 3.0

GAP_POLL_SECONDS = 0.2


def expand(rows: list[RunEventRecord]) -> list[RunEvent]:

    """Turn saved rows back into numbered events, splitting each group of reply pieces into one delta per piece."""

    events = []

    for row in rows:

        if row.event_type == ASSISTANT_DELTA:

            events.extend(RunEvent(ASSISTANT_DELTA, {"text": part["text"]}, part["seq"]) for part in row.payload["parts"])

            continue

        events.append(RunEvent(row.event_type, row.payload, row.seq))

    return events


async def saved_events(run_id: int, after: int) -> list[RunEvent]:

    """Return the run's saved events numbered above after, in order."""

    async with SessionLocal() as session:
        rows = await RunEventRepository(session).list_after(run_id, after)

    return [event for event in expand(rows) if event.seq > after]


async def run_status(run_id: int) -> RunStatus | None:

    """Return the run's saved status."""

    async with SessionLocal() as session:
        return await RunRepository(session).get_status(run_id)


async def ending_from_status(run_id: int, status: RunStatus) -> RunEvent | None:

    """Build the closing event of a run that ended or paused without a saved one, from its approval or its assistant message."""

    async with SessionLocal() as session:

        if status == RunStatus.awaiting_approval:

            approval = await ApprovalRepository(session).pending_for_run(run_id)

            return approval_event(approval) if approval is not None else None

        final_event = FINAL_EVENT_FOR_STATUS.get(status)

        if final_event is None:
            return None

        message = await RunRepository(session).get_assistant_message(run_id)

    text = message.content.get("text", "") if message is not None else ""

    return RunEvent(final_event, {"status": status.value, "text": text})


def closing_event(events: list[RunEvent], status: RunStatus | None) -> RunEvent | None:

    """Return the last saved event when it closes the stream now: a final event, or a pause the run is still waiting on."""

    if not events:
        return None

    last = events[-1]

    if last.name in FINAL_EVENTS:
        return last

    if last.name == APPROVAL_REQUIRED and status == RunStatus.awaiting_approval:
        return last

    return None


def catch_up(events: list[RunEvent], after: int, closing: RunEvent | None) -> list[RunEvent]:

    """The events a listener that saw up to after is missing: every other step since then, the whole reply so far as one snapshot, then the closing event."""

    missed = [
        event
        for event in events
        if event.seq > after and event.name != ASSISTANT_DELTA and event.name not in STREAM_END_EVENTS
        ]

    text = "".join(event.data["text"] for event in events if event.name == ASSISTANT_DELTA)

    if text:
        missed.append(RunEvent(ASSISTANT_SNAPSHOT, {"text": text}, events[-1].seq))

    if closing is not None:
        missed.append(closing)

    return missed


async def fill_gap(run_id: int, last: int, upto: int) -> list[RunEvent]:

    """Wait briefly for the events numbered between last and upto to be saved, and return those found."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + GAP_WAIT_SECONDS
    found: list[RunEvent] = []

    while True:

        found = [event for event in await saved_events(run_id, last) if event.seq < upto]

        if (found and found[-1].seq == upto - 1) or loop.time() >= deadline:
            break

        await asyncio.sleep(GAP_POLL_SECONDS)

    if not found or found[-1].seq != upto - 1:
        log.warning("run %s events %s to %s never arrived for a listener", run_id, last + 1, upto - 1)

    return found


async def follow(run_id: int, after: int) -> AsyncIterator[str]:

    """Yield the run's events as server-sent event text from after onward, ending on its final event or a pause, with keepalives while it is quiet."""

    pubsub = get_redis().pubsub()

    try:

        await pubsub.subscribe(events_channel(run_id))

        status = await run_status(run_id)
        events = await saved_events(run_id, 0)
        closing = closing_event(events, status)

        if closing is None and status is not None and status not in (RunStatus.queued, RunStatus.running, RunStatus.cancel_requested):
            closing = await ending_from_status(run_id, status)

        for event in catch_up(events, after, closing):
            yield event.to_sse()

        if closing is not None:
            return

        last = events[-1].seq if events else 0
        quiet_polls = 0

        while True:

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_SECONDS)

            if message is None:

                quiet_polls += 1

                if quiet_polls % KEEPALIVE_EVERY_POLLS == 0:
                    yield KEEPALIVE

                if quiet_polls % STATUS_CHECK_EVERY_POLLS == 0:

                    status = await run_status(run_id)

                    if status in (RunStatus.queued, RunStatus.running, RunStatus.cancel_requested):
                        continue

                    missed = await saved_events(run_id, last)

                    for event in missed:

                        yield event.to_sse()

                        if event.name in STREAM_END_EVENTS:
                            return

                    ending = await ending_from_status(run_id, status) if status is not None else None

                    if ending is not None:
                        yield ending.to_sse()

                    return

                continue

            quiet_polls = 0
            event = RunEvent.from_wire(message["data"])

            if event.seq <= last:
                continue

            if event.seq > last + 1:

                for missed in await fill_gap(run_id, last, event.seq):
                    yield missed.to_sse()

            yield event.to_sse()

            last = event.seq

            if event.name in STREAM_END_EVENTS:
                return

    finally:

        await pubsub.aclose()
