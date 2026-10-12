"""Database reads and writes for agent runs and the messages they produce."""

from collections.abc import Iterable

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ACTIVE_RUN_STATUSES, ConversationStatus, MessageRole, MessageStatus, RunStatus
from app.db.models import AgentRun, Conversation, Message


FINAL_RUN_STATUSES = (RunStatus.completed, RunStatus.cancelled, RunStatus.failed)

STATUS_TIMESTAMPS = {
    RunStatus.running: "started_at",
    RunStatus.cancel_requested: "cancel_requested_at",
    RunStatus.cancelled: "finished_at",
    RunStatus.completed: "finished_at",
    RunStatus.failed: "finished_at",
    }


class RunRepository:

    """All run and message queries for one request, sharing that request's session."""

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
        ) -> tuple[AgentRun, Message, Message]:

        """Add a queued run, the user message and an empty streaming assistant message, without committing."""

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
            content={"text": user_text},
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
        ) -> bool:

        """End the run, if it is in one of from_statuses, and its streaming assistant message with the same final status."""

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

        return True

    async def fail_active_runs(self, failure_code: str) -> list[int]:

        """Fail every run still queued, running or cancelling, fail their streaming messages, and return the run ids."""

        run_query = (
            update(AgentRun)
            .where(AgentRun.status.in_(ACTIVE_RUN_STATUSES))
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

        return run_ids
