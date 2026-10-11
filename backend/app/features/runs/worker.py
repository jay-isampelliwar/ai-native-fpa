"""The background work for one run: mark it running, stream the agent's reply, save it, and end the run."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, HumanMessage

from app.agent import graph as planner
from app.agent.context import PlannerContext
from app.db.enums import RunStatus
from app.db.session import SessionLocal
from app.features.runs.events import (
    ASSISTANT_DELTA,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    RunEvent,
    run_events,
    )
from app.features.runs.repository import RunRepository


log = logging.getLogger(__name__)

SAVE_INTERVAL_SECONDS = 1.0


async def mark_running(run_id: int) -> bool:

    """Move the run from queued to running in its own short session, and say whether it moved."""

    async with SessionLocal() as session:

        moved = await RunRepository(session).set_run_status(run_id, [RunStatus.queued], RunStatus.running)

        await session.commit()

    return moved


async def save_partial(message_id: int, text: str) -> None:

    """Save the reply text so far in its own short session."""

    async with SessionLocal() as session:

        await RunRepository(session).save_assistant_text(message_id, text)

        await session.commit()


async def end_run(
    run_id: int,
    message_id: int,
    final_status: RunStatus,
    final_text: str,
    failure_code: str | None = None,
    failure_message: str | None = None,
    ) -> None:

    """End the run and its assistant message with the final status and text in its own short session."""

    async with SessionLocal() as session:

        await RunRepository(session).finish_run(
            run_id,
            message_id,
            final_status,
            final_text=final_text,
            failure_code=failure_code,
            failure_message=failure_message,
            )

        await session.commit()


async def stream_reply(
    conversation_id: int,
    user_id: int,
    user_text: str,
    ) -> AsyncIterator[str]:

    """Run the graph on the conversation's own thread for this user and yield each piece of reply text as it arrives."""

    config = {"configurable": {"thread_id": str(conversation_id)}}
    context = PlannerContext(user_id=user_id)
    graph_input = {"messages": [HumanMessage(content=user_text)]}

    async for chunk, _ in planner.planner_graph.astream(
        graph_input,
        config=config,
        context=context,
        stream_mode="messages",
        ):

        if isinstance(chunk, AIMessageChunk) and chunk.content:
            yield chunk.content


async def execute_run(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    user_text: str,
    ) -> None:

    """Take a queued run, stream and publish the reply while saving it every second, then end it as completed, failed or cancelled."""

    reply = ""
    last_saved_at = time.monotonic()

    try:

        if not await mark_running(run_id):
            return

        async for piece in stream_reply(conversation_id, user_id, user_text):

            reply += piece

            run_events.publish(run_id, RunEvent(ASSISTANT_DELTA, {"text": piece}))

            if time.monotonic() - last_saved_at >= SAVE_INTERVAL_SECONDS:

                await save_partial(assistant_message_id, reply)

                last_saved_at = time.monotonic()

    except asyncio.CancelledError:

        log.info("run %s cancelled on conversation %s", run_id, conversation_id)

        await end_run(run_id, assistant_message_id, RunStatus.cancelled, reply)

        run_events.publish(run_id, RunEvent(RUN_CANCELLED, {"text": reply}))

        raise

    except Exception as exc:

        log.exception("run %s failed on conversation %s", run_id, conversation_id)

        await end_run(
            run_id,
            assistant_message_id,
            RunStatus.failed,
            reply,
            failure_code="agent_error",
            failure_message=str(exc)[:1000],
            )

        run_events.publish(run_id, RunEvent(RUN_FAILED, {"message": "The agent could not answer. Please try again."}))

        return

    await end_run(run_id, assistant_message_id, RunStatus.completed, reply)

    run_events.publish(run_id, RunEvent(RUN_COMPLETED, {"text": reply}))


async def fail_orphaned_runs() -> list[int]:

    """On startup, fail runs a previous process left active, since no task here is running them."""

    # TODO(runs): with several workers, only fail runs whose heartbeat is stale, or a restart kills live runs elsewhere.
    async with SessionLocal() as session:

        run_ids = await RunRepository(session).fail_active_runs(failure_code="worker_restart")

        await session.commit()

    if run_ids:
        log.warning("failed %s runs left active by a previous process: %s", len(run_ids), run_ids)

    return run_ids
