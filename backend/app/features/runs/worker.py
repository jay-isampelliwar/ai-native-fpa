"""The background work for one run: mark it running, stream and save the agent's reply and tool steps, pause for approval or end the run."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, ToolCall, ToolMessage
from langgraph.types import Command

from app.agent import graph as planner
from app.agent.approval import REJECTED_FLAG
from app.agent.context import PlannerContext
from app.agent.tools.labels import label_for
from app.db.enums import RunStatus, ToolCallStatus
from app.db.models import ToolApproval
from app.db.session import SessionLocal
from app.features.approvals.repository import ApprovalRepository
from app.features.outbox.repository import OutboxRepository
from app.features.profile.service import ProfileService
from app.features.runs.events import (
    APPROVAL_REQUIRED,
    ASSISTANT_DELTA,
    FINAL_EVENT_FOR_STATUS,
    RUN_CANCELLED,
    RUN_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    RunEvent,
    run_events,
    )
from app.features.runs.repository import RunRepository


log = logging.getLogger(__name__)

SAVE_INTERVAL_SECONDS = 1.0

INTERRUPT_KEY = "__interrupt__"

TOOL_EVENT_STATUS = {
    ToolCallStatus.completed: "ok",
    ToolCallStatus.failed: "error",
    ToolCallStatus.rejected: "rejected",
    }


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
    conversation_id: int,
    user_id: int,
    message_id: int,
    final_status: RunStatus,
    final_text: str,
    failure_code: str | None = None,
    failure_message: str | None = None,
    ) -> None:

    """End the run and its assistant message, and on completion add a memory extract event in the same commit."""

    async with SessionLocal() as session:

        ended = await RunRepository(session).finish_run(
            run_id,
            message_id,
            final_status,
            final_text=final_text,
            failure_code=failure_code,
            failure_message=failure_message,
            )

        if ended and final_status == RunStatus.completed:
            await OutboxRepository(session).add_memory_extract(run_id, conversation_id, user_id)

        await session.commit()


async def save_tool_started(
    conversation_id: int,
    message_id: int,
    run_id: int,
    call: ToolCall,
    ) -> None:

    """Save one tool call the agent asked for, in its own short session."""

    async with SessionLocal() as session:

        await RunRepository(session).add_tool_call(
            conversation_id,
            message_id,
            run_id,
            call["id"],
            call["name"],
            call["args"],
            )

        await session.commit()


async def save_tool_finished(conversation_id: int, message: ToolMessage) -> None:

    """Save how one tool call ended, with its output or its error, in its own short session."""

    content = message.content if isinstance(message.content, str) else str(message.content)
    failed = message.status == "error"

    async with SessionLocal() as session:

        await RunRepository(session).finish_tool_call(
            conversation_id,
            message.tool_call_id,
            tool_call_status(message),
            output=None if failed else {"text": content},
            error_text=content if failed else None,
            )

        await session.commit()


async def save_pause(
    run_id: int,
    conversation_id: int,
    user_id: int,
    message_id: int,
    text: str,
    request: dict[str, Any],
    ) -> ToolApproval | None:

    """Move the run to awaiting approval, hold its tool call, save the reply so far and add the pending approval, in one commit."""

    async with SessionLocal() as session:

        runs = RunRepository(session)

        if not await runs.set_run_status(run_id, [RunStatus.running], RunStatus.awaiting_approval):
            return None

        await runs.save_assistant_text(message_id, text)

        await runs.set_tool_call_status(
            conversation_id,
            request["tool_call_id"],
            [ToolCallStatus.running],
            ToolCallStatus.awaiting_approval,
            )

        approval = await ApprovalRepository(session).add_pending(
            user_id,
            conversation_id,
            run_id,
            request["tool_call_id"],
            request["name"],
            request["args"],
            request["preview"],
            )

        await session.commit()

    return approval


async def saved_reply(run_id: int) -> str:

    """Read the reply text a paused run saved, to carry on from it after the user decides."""

    async with SessionLocal() as session:
        message = await RunRepository(session).get_assistant_message(run_id)

    if message is None:
        return ""

    return message.content.get("text", "")


def tool_call_status(message: ToolMessage) -> ToolCallStatus:

    """The saved status for a finished tool call: rejected by the user, failed, or completed."""

    if message.additional_kwargs.get(REJECTED_FLAG):
        return ToolCallStatus.rejected

    if message.status == "error":
        return ToolCallStatus.failed

    return ToolCallStatus.completed


def approval_event(approval: ToolApproval) -> RunEvent:

    """The event that shows the user the Approve / Reject card for one paused tool call."""

    return RunEvent(
        APPROVAL_REQUIRED,
        {
            "approval_id": approval.id,
            "run_id": approval.run_id,
            "name": approval.tool_name,
            "label": label_for(approval.tool_name),
            "preview": approval.preview,
            "expires_at": approval.expires_at.isoformat(),
            },
        )


def update_messages(update: dict[str, Any]) -> list[AnyMessage]:

    """Return every message the nodes in one graph update added."""

    messages = []

    for node_update in update.values():

        if isinstance(node_update, dict):
            messages.extend(node_update.get("messages", []))

    return messages


def started_event(call: ToolCall) -> RunEvent:

    """The event for a tool the agent just asked for."""

    return RunEvent(TOOL_STARTED, {"id": call["id"], "name": call["name"], "label": label_for(call["name"])})


def finished_event(message: ToolMessage) -> RunEvent:

    """The event for a tool that just ran, marked ok, error or rejected."""

    name = message.name or ""
    status = TOOL_EVENT_STATUS[tool_call_status(message)]

    return RunEvent(TOOL_FINISHED, {"id": message.tool_call_id, "name": name, "label": label_for(name), "status": status})


async def stream_events(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    graph_input: dict[str, Any] | Command,
    ) -> AsyncIterator[RunEvent]:

    """Run or resume the graph on the conversation's own thread, save each tool step, and yield each reply piece, tool step and pause."""

    async with SessionLocal() as session:
        profile = await ProfileService(session).get_profile(user_id)

    config = {"configurable": {"thread_id": str(conversation_id)}}
    context = PlannerContext(user_id=user_id, profile=profile)

    async for mode, chunk in planner.planner_graph.astream(
        graph_input,
        config=config,
        context=context,
        stream_mode=["messages", "updates"],
        ):

        if mode == "updates":

            for interrupt in chunk.get(INTERRUPT_KEY, ()):
                yield RunEvent(APPROVAL_REQUIRED, interrupt.value)

            for message in update_messages(chunk):

                if isinstance(message, AIMessage):

                    for call in message.tool_calls:

                        await save_tool_started(conversation_id, assistant_message_id, run_id, call)

                        yield started_event(call)

                if isinstance(message, ToolMessage):

                    await save_tool_finished(conversation_id, message)

                    yield finished_event(message)

            continue

        message, _ = chunk

        if isinstance(message, AIMessageChunk) and message.content:
            yield RunEvent(ASSISTANT_DELTA, {"text": message.content})


async def drive_run(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    graph_input: dict[str, Any] | Command,
    reply: str,
    final_status: RunStatus = RunStatus.completed,
    ) -> None:

    """Stream and publish the reply while saving it every second, then pause for approval or end the run with final_status, failed or cancelled."""

    last_saved_at = time.monotonic()

    try:

        async for event in stream_events(run_id, conversation_id, user_id, assistant_message_id, graph_input):

            if event.name == APPROVAL_REQUIRED:

                approval = await save_pause(run_id, conversation_id, user_id, assistant_message_id, reply, event.data)

                if approval is None:
                    raise asyncio.CancelledError

                run_events.publish(run_id, approval_event(approval))

                return

            if event.name == ASSISTANT_DELTA:
                reply += event.data["text"]

            run_events.publish(run_id, event)

            if time.monotonic() - last_saved_at >= SAVE_INTERVAL_SECONDS:

                await save_partial(assistant_message_id, reply)

                last_saved_at = time.monotonic()

    except asyncio.CancelledError:

        log.info("run %s cancelled on conversation %s", run_id, conversation_id)

        await end_run(run_id, conversation_id, user_id, assistant_message_id, RunStatus.cancelled, reply)

        run_events.publish(run_id, RunEvent(RUN_CANCELLED, {"text": reply}))

        raise

    except Exception as exc:

        log.exception("run %s failed on conversation %s", run_id, conversation_id)

        await end_run(
            run_id,
            conversation_id,
            user_id,
            assistant_message_id,
            RunStatus.failed,
            reply,
            failure_code="agent_error",
            failure_message=str(exc)[:1000],
            )

        run_events.publish(run_id, RunEvent(RUN_FAILED, {"message": "The agent could not answer. Please try again."}))

        return

    await end_run(run_id, conversation_id, user_id, assistant_message_id, final_status, reply)

    run_events.publish(run_id, RunEvent(FINAL_EVENT_FOR_STATUS[final_status], {"text": reply}))


async def execute_run(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    user_text: str,
    ) -> None:

    """Take a queued run and drive the graph from the user's new message."""

    if not await mark_running(run_id):
        return

    graph_input = {"messages": [HumanMessage(content=user_text)]}

    await drive_run(run_id, conversation_id, user_id, assistant_message_id, graph_input, "")


async def resume_run(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    answer: dict[str, Any],
    final_status: RunStatus = RunStatus.completed,
    ) -> None:

    """Carry on a run that was decided, passing the answer back to the paused approval gate."""

    reply = await saved_reply(run_id)
    graph_input = Command(resume=answer)

    await drive_run(run_id, conversation_id, user_id, assistant_message_id, graph_input, reply, final_status)


async def fail_orphaned_runs() -> list[int]:

    """On startup, fail runs a previous process left active, since no task here is running them."""

    # TODO(runs): with several workers, only fail runs whose heartbeat is stale, or a restart kills live runs elsewhere.
    async with SessionLocal() as session:

        run_ids = await RunRepository(session).fail_active_runs(failure_code="worker_restart")

        await session.commit()

    if run_ids:
        log.warning("failed %s runs left active by a previous process: %s", len(run_ids), run_ids)

    return run_ids
