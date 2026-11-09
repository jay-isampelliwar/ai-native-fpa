"""The work for one run: take it for this worker, keep its heartbeat, stream and save the reply and tool steps, then pause for approval or end the run."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, ToolCall, ToolMessage
from langgraph.types import Command

from app.agent import graph as planner
from app.agent.budget import cost_usd
from app.agent.cancellation import RunCancelled
from app.agent.context import PlannerContext
from app.agent.nodes import REPAIR_NODE
from app.agent.tools.limits import turn_deadline
from app.agent.tools.labels import label_for
from app.db.enums import RunStatus, ToolCallStatus
from app.db.models import ToolApproval
from app.core.config import get_settings
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
    UI_BLOCK,
    RunEvent,
    )
from app.features.runs.publisher import RunPublisher
from app.features.runs.registry import WORKER_ID
from app.features.runs.repository import RunEventRepository, RunRepository
from app.observability.langfuse import langfuse_handler, tracing_context


log = logging.getLogger(__name__)

SAVE_INTERVAL_SECONDS = 1.0

INTERRUPT_KEY = "__interrupt__"

FAILED_TEXT = "The agent could not answer. Please try again."

TURN_TIMEOUT_TEXT = "This took too long. Please try again."

TOOL_EVENT_STATUS = {
    ToolCallStatus.completed: "ok",
    ToolCallStatus.failed: "error",
    ToolCallStatus.rejected: "rejected",
    }

TURN_SPAN_NAME = "agent-turn"


async def claim_run(run_id: int, starting: bool) -> bool:

    """Take the run for this worker in its own short session, a queued one when starting or a decided one when resuming, and say whether it was taken."""

    async with SessionLocal() as session:

        claimed = await RunRepository(session).claim_run(run_id, WORKER_ID, starting)

        await session.commit()

    return claimed


async def beat_forever(run_id: int) -> None:

    """Refresh the run's heartbeat on a fixed interval until cancelled, so the stale check knows this worker is alive."""

    interval = get_settings().RUN_HEARTBEAT_SECONDS

    while True:

        await asyncio.sleep(interval)

        try:

            async with SessionLocal() as session:

                owned = await RunRepository(session).beat(run_id, WORKER_ID)

                await session.commit()

            if not owned:
                log.warning("run %s is no longer held by worker %s", run_id, WORKER_ID)

        except Exception:
            log.exception("heartbeat of run %s failed", run_id)


@asynccontextmanager
async def heartbeat(run_id: int) -> AsyncIterator[None]:

    """Keep the run's heartbeat going while the block runs."""

    task = asyncio.create_task(beat_forever(run_id), name=f"heartbeat-{run_id}")

    try:
        yield

    finally:

        task.cancel()

        with suppress(asyncio.CancelledError):
            await task


async def save_partial(message_id: int, text: str) -> None:

    """Save the reply text so far in its own short session."""

    async with SessionLocal() as session:

        await RunRepository(session).save_assistant_text(message_id, text)

        await session.commit()


def thread_config(conversation_id: int) -> dict[str, Any]:

    """The graph config for the conversation's own thread, with a step limit above the turn's own limits as a last safety net."""

    return {
        "configurable": {"thread_id": str(conversation_id)},
        "recursion_limit": get_settings().GRAPH_RECURSION_LIMIT,
        }


def traced_config(conversation_id: int) -> dict[str, Any]:

    """The thread's graph config with the Langfuse handler attached and the turn's root span named, or the plain config when tracing is off."""

    config = thread_config(conversation_id)
    handler = langfuse_handler(get_settings())

    if handler is None:
        return config

    return {**config, "callbacks": [handler], "run_name": TURN_SPAN_NAME}


async def turn_usage(conversation_id: int) -> tuple[dict[str, Any], str | None]:

    """Read what the turn used from the graph's saved state, with its cost, and the limit it reached, if any."""

    graph = getattr(planner, "planner_graph", None)

    if graph is None:
        return {}, None

    try:
        snapshot = await graph.aget_state(thread_config(conversation_id))

    except Exception:

        log.exception("could not read the usage of the turn on conversation %s", conversation_id)

        return {}, None

    budget = snapshot.values.get("budget")

    if not budget:
        return {}, None

    usage = {
        "model_calls": budget["model_calls"],
        "tool_calls": budget["tool_calls"],
        "input_tokens": budget["input_tokens"],
        "output_tokens": budget["output_tokens"],
        "cost_usd": cost_usd(budget, get_settings().CHAT_MODEL),
        }

    return usage, budget["limit"]


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

    """End the run with its usage and its assistant message, noting a limit it reached, and on completion add a memory extract event."""

    usage, limit = await turn_usage(conversation_id)

    if failure_code is None and final_status == RunStatus.completed:
        failure_code = limit

    async with SessionLocal() as session:

        ended = await RunRepository(session).finish_run(
            run_id,
            message_id,
            final_status,
            final_text=final_text,
            failure_code=failure_code,
            failure_message=failure_message,
            usage=usage,
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

    """Save how one tool call ended, with its typed result as the output and its message as the error, in its own short session."""

    result = tool_result(message)
    failed = message.status == "error"

    async with SessionLocal() as session:

        await RunRepository(session).finish_tool_call(
            conversation_id,
            message.tool_call_id,
            tool_call_status(message),
            output=result,
            error_text=result.get("message") if failed else None,
            )

        await session.commit()


async def save_pause(
    run_id: int,
    conversation_id: int,
    user_id: int,
    message_id: int,
    text: str,
    request: dict[str, Any],
    seq: int,
    ) -> ToolApproval | None:

    """Move the run to awaiting approval and release it, hold its tool call, save the reply so far, the pending approval and its event numbered seq, in one commit."""

    async with SessionLocal() as session:

        runs = RunRepository(session)

        if not await runs.set_run_status(run_id, [RunStatus.running], RunStatus.awaiting_approval):
            return None

        await runs.release_run(run_id)

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

        event = approval_event(approval)

        await RunEventRepository(session).add(run_id, seq, event.name, event.data)

        await session.commit()

    return approval


async def saved_reply(run_id: int) -> str:

    """Read the reply text a paused run saved, to carry on from it after the user decides."""

    async with SessionLocal() as session:
        message = await RunRepository(session).get_assistant_message(run_id)

    if message is None:
        return ""

    return message.content.get("text", "")


def tool_result(message: ToolMessage) -> dict[str, Any]:

    """The typed result a tool sent as its artifact, or its plain text for a message without one."""

    if isinstance(message.artifact, dict):
        return message.artifact

    content = message.content if isinstance(message.content, str) else str(message.content)

    return {"message": content}


def tool_call_status(message: ToolMessage) -> ToolCallStatus:

    """The saved status for a finished tool call: rejected by the user, failed, or completed."""

    if tool_result(message).get("status") == "rejected":
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

    """Return every message the nodes in one graph update added, leaving out the repair's rewrite of old history."""

    messages = []

    for node, node_update in update.items():

        if node == REPAIR_NODE:
            continue

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


def block_event(message: ToolMessage) -> RunEvent | None:

    """The event that hands the chat a tool's card or form, keyed by its tool call id, or None when it sent neither."""

    result = tool_result(message)
    block = result.get("block")

    if result.get("status") != "success" or not isinstance(block, dict):
        return None

    return RunEvent(UI_BLOCK, {"id": message.tool_call_id, "block": block})


def spaced(
    text: Any,
    gap: bool,
    ) -> Any:

    """Start the text on a new paragraph when tools ran after earlier text, so two pieces of the reply never run together."""

    if gap and isinstance(text, str):
        return f"\n\n{text}"

    return text


async def stream_events(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    graph_input: dict[str, Any] | Command,
    deadline: float,
    ) -> AsyncIterator[RunEvent]:

    """Run or resume the graph on the conversation's own thread by the deadline, save each tool step, and yield each piece, step and pause, with a paragraph break after tools."""

    async with SessionLocal() as session:
        profile = await ProfileService(session).get_profile(user_id)

    config = traced_config(conversation_id)
    context = PlannerContext(
        user_id=user_id,
        profile=profile,
        conversation_id=conversation_id,
        run_id=run_id,
        deadline=deadline,
        )

    wrote = False
    gap = False

    async for mode, chunk in planner.planner_graph.astream(
        graph_input,
        config=config,
        context=context,
        stream_mode=["messages", "updates"],
        ):

        if mode == "updates":

            gap = gap or (wrote and bool(update_messages(chunk)))

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

                    block = block_event(message)

                    if block is not None:
                        yield block

            continue

        message, _ = chunk

        if isinstance(message, AIMessageChunk) and message.content:

            yield RunEvent(ASSISTANT_DELTA, {"text": spaced(message.content, gap)})

            wrote = True
            gap = False


async def drive_run(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    graph_input: dict[str, Any] | Command,
    reply: str,
    final_status: RunStatus = RunStatus.completed,
    ) -> None:

    """Stream and publish the reply within the turn's time budget, saving it every second, then pause, or end it as final_status, failed or cancelled."""

    publisher = await RunPublisher(run_id).open()
    last_saved_at = time.monotonic()
    deadline = turn_deadline()
    turn = asyncio.timeout(get_settings().TURN_TIMEOUT_SECONDS)

    failure_code = "agent_error"
    failure_text = FAILED_TEXT

    try:

        async with turn:

            with tracing_context(get_settings(), user_id, conversation_id, run_id, WORKER_ID):

                async for event in stream_events(run_id, conversation_id, user_id, assistant_message_id, graph_input, deadline):

                    if event.name == APPROVAL_REQUIRED:

                        await publisher.flush()

                        seq = publisher.seq + 1

                        approval = await save_pause(run_id, conversation_id, user_id, assistant_message_id, reply, event.data, seq)

                        if approval is None:
                            raise asyncio.CancelledError

                        await publisher.send_saved(approval_event(approval), seq)

                        return

                    if event.name == ASSISTANT_DELTA:
                        reply += event.data["text"]

                    await publisher.emit(event)

                    if time.monotonic() - last_saved_at >= SAVE_INTERVAL_SECONDS:

                        await save_partial(assistant_message_id, reply)

                        last_saved_at = time.monotonic()

    except RunCancelled:

        log.info("run %s stopped on its saved cancel on conversation %s", run_id, conversation_id)

        await end_run(run_id, conversation_id, user_id, assistant_message_id, RunStatus.cancelled, reply)

        await publisher.emit(RunEvent(RUN_CANCELLED, {"text": reply}))

        return

    except asyncio.CancelledError:

        log.info("run %s cancelled on conversation %s", run_id, conversation_id)

        await end_run(run_id, conversation_id, user_id, assistant_message_id, RunStatus.cancelled, reply)

        await publisher.emit(RunEvent(RUN_CANCELLED, {"text": reply}))

        raise

    except Exception as exc:

        if isinstance(exc, TimeoutError) and turn.expired():

            failure_code = "turn_timeout"
            failure_text = TURN_TIMEOUT_TEXT

        log.exception("run %s failed on conversation %s with %s", run_id, conversation_id, failure_code)

        await end_run(
            run_id,
            conversation_id,
            user_id,
            assistant_message_id,
            RunStatus.failed,
            reply,
            failure_code=failure_code,
            failure_message=str(exc)[:1000] or failure_text,
            )

        await publisher.emit(RunEvent(RUN_FAILED, {"message": failure_text}))

        return

    await end_run(run_id, conversation_id, user_id, assistant_message_id, final_status, reply)

    await publisher.emit(RunEvent(FINAL_EVENT_FOR_STATUS[final_status], {"text": reply}))


async def start_claimed(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    user_text: str,
    ) -> None:

    """Drive a run this worker already took from the user's new message, with its heartbeat going."""

    graph_input = {"messages": [HumanMessage(content=user_text)]}

    async with heartbeat(run_id):
        await drive_run(run_id, conversation_id, user_id, assistant_message_id, graph_input, "")


async def resume_claimed(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    answer: dict[str, Any],
    final_status: RunStatus = RunStatus.completed,
    ) -> None:

    """Carry on a decided run this worker already took, passing the answer back to the paused approval gate, with its heartbeat going."""

    reply = await saved_reply(run_id)
    graph_input = Command(resume=answer)

    async with heartbeat(run_id):
        await drive_run(run_id, conversation_id, user_id, assistant_message_id, graph_input, reply, final_status)


async def execute_run(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    user_text: str,
    ) -> None:

    """Take a queued run for this worker and drive the graph from the user's new message."""

    if not await claim_run(run_id, starting=True):
        return

    await start_claimed(run_id, conversation_id, user_id, assistant_message_id, user_text)


async def resume_run(
    run_id: int,
    conversation_id: int,
    user_id: int,
    assistant_message_id: int,
    answer: dict[str, Any],
    final_status: RunStatus = RunStatus.completed,
    ) -> None:

    """Take a decided run for this worker and carry it on from the paused approval gate."""

    if not await claim_run(run_id, starting=False):
        return

    await resume_claimed(run_id, conversation_id, user_id, assistant_message_id, answer, final_status)
