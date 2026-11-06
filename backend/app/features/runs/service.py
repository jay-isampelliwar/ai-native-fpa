"""Business rules for starting a run: find or create the conversation, then reuse or create the run."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.forms import FORM_TITLES
from app.db.models import Conversation
from app.db.enums import RunStatus
from app.features.approvals.service import CANCELLED, NEW_MESSAGE, ApprovalService
from app.features.conversations.titles import title_from
from app.features.runs.events import RUN_CANCELLED, RunEvent
from app.features.runs.exceptions import ConversationNotFound, RunAlreadyActive, RunNotFound
from app.features.runs.jobs import START, RunJob, submit
from app.features.runs.publisher import record_event, signal_cancel
from app.features.runs.registry import run_registry
from app.features.runs.repository import RunRepository
from app.features.runs.schemas import CreateRunRequest, RunResponse



DUPLICATE_REQUEST_CONSTRAINT = "uq_agent_runs_conversation_client_request"
ONE_ACTIVE_RUN_CONSTRAINT = "uq_agent_runs_one_active"


def violated_constraint(exc: IntegrityError) -> str | None:

    """Read the name of the unique constraint Postgres says the insert broke."""

    diag = getattr(exc.orig, "diag", None)

    return getattr(diag, "constraint_name", None)


class RunService:

    """The steps behind POST /runs for one request, sharing that request's session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the request's session and build the repository on top of it."""

        self.session = session
        self.repo = RunRepository(session)

    async def resolve_conversation(
        self,
        conversation_id: int | None,
        user_id: int,
        first_message: str,
        ) -> Conversation:

        """Create a conversation titled from the first message when none is given, otherwise load it and refuse one this user does not own."""

        if conversation_id is None:
            return await self.repo.create_conversation(user_id, title_from(first_message))

        conversation = await self.repo.get_conversation(conversation_id, user_id)

        if conversation is None:
            raise ConversationNotFound(conversation_id)

        return conversation

    async def create_run(self, body: CreateRunRequest, user_id: int) -> RunResponse:

        """Return the existing run for a retried request, or reject any pending approval, save a new run with its two messages, commit, and start it."""

        first_message = f"{FORM_TITLES[body.form.kind]} details" if body.form is not None else body.message

        conversation = await self.resolve_conversation(body.conversation_id, user_id, first_message)

        conversation_id = conversation.id

        existing = await self.repo.find_run_by_request(conversation_id, body.client_request_id)

        if existing is not None:
            return RunResponse.from_run(existing)

        await ApprovalService(self.session).close_pending_in(conversation_id, NEW_MESSAGE)

        try:
            run, _, assistant_message = await self.repo.create_run_with_messages(
                conversation_id,
                body.client_request_id,
                body.message,
                body.form.saved() if body.form is not None else None,
                )

            await self.session.commit()

        except IntegrityError as exc:

            await self.session.rollback()

            return await self.recover_from_conflict(exc, conversation_id, body.client_request_id)

        await submit(RunJob(START, run.id, conversation_id, user_id, assistant_message.id, user_text=body.message))

        return RunResponse.from_run(run)

    async def cancel_run(self, run_id: int, user_id: int) -> RunResponse:

        """Stop the run: end a queued or paused one at once, ask a running one's task to stop, and leave an ended one alone."""

        run = await self.repo.get_run_for_user(run_id, user_id)

        if run is None:
            raise RunNotFound(run_id)

        if run.status == RunStatus.awaiting_approval:

            await ApprovalService(self.session).close_pending_in(run.conversation_id, CANCELLED)

            await self.session.refresh(run)

            return RunResponse.from_run(run)

        if run.status == RunStatus.queued and await self.cancel_queued(run_id):
            await self.session.refresh(run)

            return RunResponse.from_run(run)

        moved = await self.repo.set_run_status(run_id, [RunStatus.running], RunStatus.cancel_requested)

        await self.session.commit()

        await self.session.refresh(run)

        if moved or run.status == RunStatus.cancel_requested:

            run_registry.cancel(run_id)

            await signal_cancel(run_id)

        return RunResponse.from_run(run)

    async def cancel_queued(self, run_id: int) -> bool:

        """End a run that has not started yet as cancelled, and say whether it was still queued."""

        message = await self.repo.get_assistant_message(run_id)

        ended = await self.repo.finish_run(
            run_id,
            message.id,
            RunStatus.cancelled,
            from_statuses=[RunStatus.queued],
            )

        await self.session.commit()

        if not ended:
            return False

        run_registry.cancel(run_id)

        await record_event(run_id, RunEvent(RUN_CANCELLED, {"text": ""}))

        return True

    async def recover_from_conflict(
        self,
        exc: IntegrityError,
        conversation_id: int,
        client_request_id: str,
        ) -> RunResponse:

        """Turn a lost insert race into the winning run, or into RunAlreadyActive when another run is still going."""

        constraint = violated_constraint(exc)

        if constraint == DUPLICATE_REQUEST_CONSTRAINT:

            winner = await self.repo.find_run_by_request(conversation_id, client_request_id)

            if winner is not None:
                return RunResponse.from_run(winner)

        if constraint == ONE_ACTIVE_RUN_CONSTRAINT:
            raise RunAlreadyActive(conversation_id) from exc

        raise exc
