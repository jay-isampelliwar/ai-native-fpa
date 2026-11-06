"""Database reads and writes for agent runs, the messages they produce and the tools they call."""

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from sqlalchemy import ColumnElement, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ACTIVE_RUN_STATUSES, ConversationStatus, MessageRole, MessageStatus, RunStatus, ToolCallStatus
from app.db.models import AgentRun, Conversation, Message, RunEventRecord, ToolCall


FINAL_RUN_STATUSES = (RunStatus.completed, RunStatus.cancelled, RunStatus.failed)

STATUS_TIMESTAMPS = {
    RunStatus.running: "started_at",
    RunStatus.cancel_requested: "cancel_requested_at",
    RunStatus.cancelled: "finished_at",
    RunStatus.completed: "finished_at",
    RunStatus.failed: "finished_at",
    }

OPEN_TOOL_STATUSES = (ToolCallStatus.requested, ToolCallStatus.running, ToolCallStatus.awaiting_approval)

WORKER_HELD_STATUSES = (RunStatus.queued, RunStatus.running, RunStatus.cancel_requested)

RESUMABLE_STATUSES = (RunStatus.running, RunStatus.cancel_requested)


def seconds_ago(seconds: float) -> ColumnElement:

    """The database time the given number of seconds before now."""

    return func.now() - timedelta(seconds=seconds)


class RunRepository:

    """All run, message and tool call queries for one request, sharing that request's session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session this request opened, so every method talks through it."""

        self.session = session

    async def get_conversation(self, conversation_id: int, user_id: int) -> Conversation | None:

        """Return the conversation only when it exists, is not deleted and belongs to this user."""

        query = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.status != ConversationStatus.deleted,
            )

        return await self.session.scalar(query)

    async def create_conversation(self, user_id: int, title: str) -> Conversation:

        """Add a new empty conversation for this user with its title, and flush it so its id is known."""

        conversation = Conversation(user_id=user_id, title=title)

        self.session.add(conversation)

        await self.session.flush()

        return conversation

    async def get_run_for_user(self, run_id: int, user_id: int) -> AgentRun | None:

        """Return the run only when its conversation belongs to this user."""

        query = (
            select(AgentRun)
            .join(Conversation, Conversation.id == AgentRun.conversation_id)
            .where(AgentRun.id == run_id, Conversation.user_id == user_id)
            )

        return await self.session.scalar(query)

    async def get_assistant_message(self, run_id: int) -> Message | None:

        """Return the assistant message this run is writing or wrote."""

        query = select(Message).where(Message.run_id == run_id, Message.role == MessageRole.assistant)

        return await self.session.scalar(query)

    async def get_user_message(self, run_id: int) -> Message | None:

        """Return the user message that started this run."""

        query = select(Message).where(Message.run_id == run_id, Message.role == MessageRole.user)

        return await self.session.scalar(query)

    async def get_owner_id(self, conversation_id: int) -> int | None:

        """Return the id of the user who owns the conversation."""

        return await self.session.scalar(select(Conversation.user_id).where(Conversation.id == conversation_id))

    async def find_run_by_request(
        self,
        conversation_id: int,
        client_request_id: str,
        ) -> AgentRun | None:

        """Return the run already created for this client request, or None when it is new."""

        query = select(AgentRun).where(
            AgentRun.conversation_id == conversation_id,
            AgentRun.client_request_id == client_request_id,
            )

        return await self.session.scalar(query)

    async def next_sequence(self, conversation_id: int, count: int = 1) -> int:

        """Reserve the next count message numbers in one locked update and return the first of them."""

        query = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(current_sequence=Conversation.current_sequence + count)
            .returning(Conversation.current_sequence)
            )

        last = await self.session.scalar(query)

        if last is None:
            raise LookupError(f"conversation {conversation_id} does not exist")

        return last - count + 1

    async def create_run_with_messages(
        self,
        conversation_id: int,
        client_request_id: str,
        user_text: str,
        form: dict[str, Any] | None = None,
        ) -> tuple[AgentRun, Message, Message]:

        """Add a queued run, the user message with its filled form if any, and an empty streaming assistant message, without committing."""

        run = AgentRun(
            conversation_id=conversation_id,
            client_request_id=client_request_id,
            status=RunStatus.queued,
            )

        self.session.add(run)

        await self.session.flush()

        first = await self.next_sequence(conversation_id, count=2)

        user_message = Message(
            conversation_id=conversation_id,
            run_id=run.id,
            sequence_number=first,
            role=MessageRole.user,
            status=MessageStatus.completed,
            content={"text": user_text, "form": form} if form is not None else {"text": user_text},
            completed_at=func.now(),
            )

        assistant_message = Message(
            conversation_id=conversation_id,
            run_id=run.id,
            sequence_number=first + 1,
            role=MessageRole.assistant,
            status=MessageStatus.streaming,
            content={"text": ""},
            )

        self.session.add_all([user_message, assistant_message])

        await self.session.flush()

        return run, user_message, assistant_message

    async def set_run_status(
        self,
        run_id: int,
        expected: Iterable[RunStatus],
        new_status: RunStatus,
        ) -> bool:

        """Move the run to new_status only if it is still in an expected status, and say whether it moved."""

        values = {"status": new_status, "version": AgentRun.version + 1}

        timestamp_column = STATUS_TIMESTAMPS.get(new_status)

        if timestamp_column is not None:
            values[timestamp_column] = func.now()

        query = (
            update(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.status.in_(list(expected)))
            .values(**values)
            .returning(AgentRun.id)
            )

        moved = await self.session.scalar(query)

        return moved is not None

    async def save_assistant_text(self, message_id: int, text: str) -> bool:

        """Overwrite the streaming assistant message with the text so far, and say whether it was still streaming."""

        query = (
            update(Message)
            .where(Message.id == message_id, Message.status == MessageStatus.streaming)
            .values(content={"text": text})
            .returning(Message.id)
            )

        saved = await self.session.scalar(query)

        return saved is not None

    async def finish_run(
        self,
        run_id: int,
        message_id: int,
        final_status: RunStatus,
        final_text: str | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
        from_statuses: Iterable[RunStatus] = ACTIVE_RUN_STATUSES,
        usage: dict[str, Any] | None = None,
        ) -> bool:

        """End the run, if it is in one of from_statuses, with its usage, and its streaming assistant message with the same status."""

        if final_status not in FINAL_RUN_STATUSES:
            raise ValueError(f"{final_status} is not a final run status")

        run_query = (
            update(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.status.in_(list(from_statuses)))
            .values(
                status=final_status,
                version=AgentRun.version + 1,
                finished_at=func.now(),
                failure_code=failure_code,
                failure_message=failure_message,
                **(usage or {}),
                )
            .returning(AgentRun.id)
            )

        ended = await self.session.scalar(run_query)

        if ended is None:
            return False

        message_values = {"status": MessageStatus(final_status.value), "completed_at": func.now()}

        if final_text is not None:
            message_values["content"] = {"text": final_text}

        message_query = (
            update(Message)
            .where(Message.id == message_id, Message.status == MessageStatus.streaming)
            .values(**message_values)
            )

        await self.session.execute(message_query)

        await self.close_open_tool_calls([run_id], final_status)

        return True

    async def fail_active_runs(self, failure_code: str, *conditions: ColumnElement) -> list[int]:

        """Fail every run a worker was holding that matches the conditions, leaving runs paused for approval, and return their ids."""

        run_query = (
            update(AgentRun)
            .where(AgentRun.status.in_(WORKER_HELD_STATUSES), *conditions)
            .values(
                status=RunStatus.failed,
                version=AgentRun.version + 1,
                finished_at=func.now(),
                failure_code=failure_code,
                )
            .returning(AgentRun.id)
            )

        run_ids = list(await self.session.scalars(run_query))

        if not run_ids:
            return []

        message_query = (
            update(Message)
            .where(Message.run_id.in_(run_ids), Message.status == MessageStatus.streaming)
            .values(status=MessageStatus.failed, completed_at=func.now())
            )

        await self.session.execute(message_query)

        await self.close_open_tool_calls(run_ids, RunStatus.failed)

        return run_ids

    async def fail_stale_runs(self, stale_seconds: float) -> list[int]:

        """Fail runs whose worker stopped sending heartbeats, and runs whose resume job never reached the queue."""

        owner_lost = await self.fail_active_runs(
            "worker_lost",
            AgentRun.worker_id.is_not(None),
            or_(AgentRun.heartbeat_at.is_(None), AgentRun.heartbeat_at < seconds_ago(stale_seconds)),
            )

        resume_unsent = await self.fail_active_runs(
            "enqueue_failed",
            AgentRun.status.in_(RESUMABLE_STATUSES),
            AgentRun.worker_id.is_(None),
            AgentRun.enqueued_at.is_(None),
            AgentRun.updated_at < seconds_ago(stale_seconds),
            )

        return owner_lost + resume_unsent

    async def unsent_queued_runs(self, older_than_seconds: float, limit: int) -> list[AgentRun]:

        """Return queued runs whose start job never reached the queue, oldest first."""

        query = (
            select(AgentRun)
            .where(
                AgentRun.status == RunStatus.queued,
                AgentRun.enqueued_at.is_(None),
                AgentRun.created_at < seconds_ago(older_than_seconds),
                )
            .order_by(AgentRun.created_at)
            .limit(limit)
            )

        return list(await self.session.scalars(query))

    async def mark_enqueued(self, run_id: int) -> None:

        """Note that the run's job is now on the queue."""

        await self.session.execute(update(AgentRun).where(AgentRun.id == run_id).values(enqueued_at=func.now()))

    async def prepare_resume(self, run_id: int) -> None:

        """Clear the owner, the sent time and the attempts, so the next resume job starts fresh."""

        query = (
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(worker_id=None, heartbeat_at=None, enqueued_at=None, attempts=0)
            )

        await self.session.execute(query)

    async def add_attempt(self, run_id: int) -> int | None:

        """Count one more time a worker took the run's job, and return the new count, or None if the run is gone."""

        query = (
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(attempts=AgentRun.attempts + 1)
            .returning(AgentRun.attempts)
            )

        return await self.session.scalar(query)

    async def claim_run(
        self,
        run_id: int,
        worker_id: str,
        starting: bool,
        ) -> bool:

        """Take an unowned run for this worker, a queued one moved to running when starting or a decided one when resuming."""

        values = {
            "worker_id": worker_id,
            "heartbeat_at": func.now(),
            "version": AgentRun.version + 1,
            }

        expected = [RunStatus.queued] if starting else list(RESUMABLE_STATUSES)

        if starting:

            values["status"] = RunStatus.running
            values["started_at"] = func.now()

        query = (
            update(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.status.in_(expected), AgentRun.worker_id.is_(None))
            .values(**values)
            .returning(AgentRun.id)
            )

        return await self.session.scalar(query) is not None

    async def beat(self, run_id: int, worker_id: str) -> bool:

        """Refresh the heartbeat of a run this worker still owns, and say whether it still owns it."""

        query = (
            update(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.worker_id == worker_id, AgentRun.status.in_(WORKER_HELD_STATUSES))
            .values(heartbeat_at=func.now())
            .returning(AgentRun.id)
            )

        return await self.session.scalar(query) is not None

    async def release_run(self, run_id: int) -> None:

        """Drop the owner of a paused run, so whichever worker gets the resume job can take it."""

        await self.session.execute(update(AgentRun).where(AgentRun.id == run_id).values(worker_id=None, heartbeat_at=None))

    async def get_status(self, run_id: int) -> RunStatus | None:

        """Return the run's status, or None if it does not exist."""

        return await self.session.scalar(select(AgentRun.status).where(AgentRun.id == run_id))

    async def add_tool_call(
        self,
        conversation_id: int,
        message_id: int,
        run_id: int,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        ) -> None:

        """Add one tool call the agent asked for, marked running from now."""

        tool_call = ToolCall(
            conversation_id=conversation_id,
            message_id=message_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            status=ToolCallStatus.running,
            started_at=func.now(),
            )

        self.session.add(tool_call)

        await self.session.flush()

    async def finish_tool_call(
        self,
        conversation_id: int,
        tool_call_id: str,
        status: ToolCallStatus,
        output: dict[str, Any] | None = None,
        error_text: str | None = None,
        ) -> None:

        """End one running tool call with its final status and its output or error."""

        query = (
            update(ToolCall)
            .where(
                ToolCall.conversation_id == conversation_id,
                ToolCall.tool_call_id == tool_call_id,
                ToolCall.status.in_(OPEN_TOOL_STATUSES),
                )
            .values(status=status, output=output, error_text=error_text, completed_at=func.now())
            )

        await self.session.execute(query)

    async def set_tool_call_status(
        self,
        conversation_id: int,
        tool_call_id: str,
        expected: Iterable[ToolCallStatus],
        new_status: ToolCallStatus,
        ) -> None:

        """Move one tool call to new_status only if it is still in an expected status."""

        query = (
            update(ToolCall)
            .where(
                ToolCall.conversation_id == conversation_id,
                ToolCall.tool_call_id == tool_call_id,
                ToolCall.status.in_(list(expected)),
                )
            .values(status=new_status)
            )

        await self.session.execute(query)

    async def close_open_tool_calls(self, run_ids: list[int], run_status: RunStatus) -> None:

        """End every tool call these runs left open, as cancelled when the run was stopped and failed otherwise."""

        status = ToolCallStatus.cancelled if run_status == RunStatus.cancelled else ToolCallStatus.failed

        query = (
            update(ToolCall)
            .where(ToolCall.run_id.in_(run_ids), ToolCall.status.in_(OPEN_TOOL_STATUSES))
            .values(status=status, completed_at=func.now())
            )

        await self.session.execute(query)


class RunEventRepository:

    """Reads and writes of the saved events of runs, sharing the caller's session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the caller's session."""

        self.session = session

    async def last_seq(self, run_id: int) -> int:

        """Return the number of the run's last saved event, or 0 when it has none."""

        query = select(func.coalesce(func.max(RunEventRecord.seq), 0)).where(RunEventRecord.run_id == run_id)

        return await self.session.scalar(query)

    async def add(
        self,
        run_id: int,
        seq: int,
        event_type: str,
        payload: dict[str, Any],
        ) -> None:

        """Save one event of the run under its number."""

        self.session.add(RunEventRecord(run_id=run_id, seq=seq, event_type=event_type, payload=payload))

        await self.session.flush()

    async def list_after(self, run_id: int, seq: int) -> list[RunEventRecord]:

        """Return the run's saved events numbered above seq, in order."""

        query = (
            select(RunEventRecord)
            .where(RunEventRecord.run_id == run_id, RunEventRecord.seq > seq)
            .order_by(RunEventRecord.seq)
            )

        return list(await self.session.scalars(query))

    async def delete_old(self, keep_hours: float) -> int:

        """Delete events older than keep_hours of runs that have ended, and return how many were deleted."""

        ended_runs = select(AgentRun.id).where(AgentRun.status.in_(FINAL_RUN_STATUSES))

        query = delete(RunEventRecord).where(
            RunEventRecord.created_at < seconds_ago(keep_hours * 3600),
            RunEventRecord.run_id.in_(ended_runs),
            )

        result = await self.session.execute(query)

        return result.rowcount
