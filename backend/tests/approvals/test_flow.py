"""End-to-end tests for approvals on real Postgres and the real checkpointer, with a fake model that asks to delete an expense and runs driven in this process instead of by the agent worker."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from sqlalchemy import select, update

from app.agent import graph as planner
from app.agent.checkpointer import open_checkpointer
from app.db.enums import ApprovalStatus, ExpenseCategory, RunStatus, ToolCallStatus
from app.db.models import AgentRun, Conversation, Expense, Message, ToolApproval, ToolCall
from app.db.session import SessionLocal
from app.features.approvals.exceptions import ApprovalExpired, ApprovalNotFound, ApprovalNotPending
from app.features.approvals.schemas import ApprovalChoice
from app.features.approvals.service import ApprovalService
from app.features.approvals.sweeper import expire_due
from app.features.runs import jobs
from app.features.runs.jobs import START, RunJob
from app.features.runs.registry import run_registry
from app.features.runs.schemas import CreateRunRequest, RunResponse
from app.features.runs.service import RunService
from app.features.runs.repository import RunRepository
from app.features.runs.worker import claim_run
from app.services import llm
from tests.support import create_user, delete_user_data


DELETE_TEXT = "delete my rent"

REPLY_TEXT = "Done."


@dataclass
class Paused:

    """A user with one rent expense, and the run that paused to ask before deleting it."""

    user_id: int
    expense_id: int
    run: RunResponse
    approval: ToolApproval


class FakeModel:

    """Asks for get_missing_data and delete_record on a delete message, and answers in one line otherwise."""

    def __init__(self, expense_id: int) -> None:

        """Keep the id of the expense the model will ask to delete."""

        self.expense_id = expense_id

    async def astream(self, messages: list) -> AsyncIterator[AIMessageChunk]:

        """Stream one tool request or one short answer."""

        last = messages[-1]

        if isinstance(last, HumanMessage) and last.content == DELETE_TEXT:

            yield AIMessageChunk(
                "",
                tool_call_chunks=[
                    {"name": "get_missing_data", "args": "{}", "id": "missing", "index": 0},
                    {
                        "name": "delete_record",
                        "args": f'{{"kind": "expenses", "record_id": {self.expense_id}}}',
                        "id": "del",
                        "index": 1,
                        },
                    ],
                )

            return

        yield AIMessageChunk(REPLY_TEXT)


@pytest.fixture(autouse=True)
def worker_in_process(monkeypatch: pytest.MonkeyPatch) -> None:

    """Stand in for the agent worker: instead of sending a job to Redis, take its run and drive it as a task in this process."""

    async def take(job: RunJob) -> bool:

        """Claim the job's run and start it here, as the agent worker would."""

        if await claim_run(job.run_id, starting=job.kind == START):
            run_registry.start(job.run_id, job.claimed_work())

        return True

    monkeypatch.setattr(jobs, "enqueue", take)


@pytest.fixture
async def paused(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Paused]:

    """Compile the planner on the real checkpointer, pause one delete run, then remove the user and their threads."""

    user_id = await create_user()

    async with open_checkpointer() as checkpointer:

        planner.planner_graph = planner.build_planner_graph(checkpointer)

        try:

            expense_id = await add_rent(user_id)

            monkeypatch.setattr(llm.llm_service, "with_tools", lambda tools, model=None, max_tokens=None: FakeModel(expense_id))

            run = await send(user_id, None, DELETE_TEXT)
            approval = await approval_for(run.run_id)

            yield Paused(user_id, expense_id, run, approval)

        finally:

            await wait_for_runs()

            async with SessionLocal() as session:
                conversation_ids = list(await session.scalars(select(Conversation.id).where(Conversation.user_id == user_id)))

            for conversation_id in conversation_ids:
                await checkpointer.adelete_thread(str(conversation_id))

            await delete_user_data(user_id)


async def add_rent(user_id: int) -> int:

    """Save one rent expense for the user and return its id."""

    async with SessionLocal() as session:

        expense = Expense(user_id=user_id, category=ExpenseCategory.rent, name="Rent", amount=Decimal("20000"))

        session.add(expense)

        await session.commit()

        return expense.id


async def wait_for_runs() -> None:

    """Wait until every background run task this process started has ended."""

    while run_registry.tasks:
        await asyncio.gather(*run_registry.tasks.values(), return_exceptions=True)


async def send(user_id: int, conversation_id: int | None, text: str) -> RunResponse:

    """Start a run for one message through the service and wait for it to end or pause."""

    body = CreateRunRequest(conversation_id=conversation_id, client_request_id=uuid4().hex, message=text)

    async with SessionLocal() as session:
        run = await RunService(session).create_run(body, user_id)

    await wait_for_runs()

    return run


async def decide(data: Paused, choice: ApprovalChoice, user_id: int | None = None) -> None:

    """Click Approve or Reject on the paused card, as the given user or the owner, and wait for the run."""

    async with SessionLocal() as session:
        await ApprovalService(session).submit(data.run.run_id, data.approval.id, user_id or data.user_id, choice)

    await wait_for_runs()


async def approval_for(run_id: int) -> ToolApproval:

    """Return the run's approval row."""

    async with SessionLocal() as session:
        return await session.scalar(select(ToolApproval).where(ToolApproval.run_id == run_id))


async def run_status(run_id: int) -> RunStatus:

    """Return the run's status."""

    async with SessionLocal() as session:
        return await session.scalar(select(AgentRun.status).where(AgentRun.id == run_id))


async def call_statuses(run_id: int) -> dict[str, ToolCallStatus]:

    """Return each of the run's tool calls by name with its status."""

    async with SessionLocal() as session:
        calls = await session.scalars(select(ToolCall).where(ToolCall.run_id == run_id))

    return {call.tool_name: call.status for call in calls}


async def reply_text(run_id: int) -> str:

    """Return the run's saved assistant text."""

    async with SessionLocal() as session:
        message = await session.scalar(select(Message).where(Message.run_id == run_id, Message.role == "assistant"))

    return message.content.get("text", "")


async def rent_exists(expense_id: int) -> bool:

    """Say whether the rent expense is still saved."""

    async with SessionLocal() as session:
        return await session.get(Expense, expense_id) is not None


async def test_delete_pauses_with_a_pending_approval(paused: Paused) -> None:

    """The run waits with its delete held, the preview names the expense, and nothing is removed."""

    assert await run_status(paused.run.run_id) == RunStatus.awaiting_approval
    assert (await call_statuses(paused.run.run_id))["delete_record"] == ToolCallStatus.awaiting_approval
    assert paused.approval.status == ApprovalStatus.pending
    assert paused.approval.preview["title"] == "Remove this expense?"
    assert {"name": "name", "value": "Rent"} in paused.approval.preview["fields"]
    assert await rent_exists(paused.expense_id)


async def test_approve_deletes_and_replies(paused: Paused) -> None:

    """Approving removes the expense, completes both calls and the run, and the agent replies."""

    await decide(paused, ApprovalChoice.approve)

    assert not await rent_exists(paused.expense_id)
    assert await run_status(paused.run.run_id) == RunStatus.completed
    assert await call_statuses(paused.run.run_id) == {
        "get_missing_data": ToolCallStatus.completed,
        "delete_record": ToolCallStatus.completed,
        }
    assert (await approval_for(paused.run.run_id)).status == ApprovalStatus.approved
    assert await reply_text(paused.run.run_id) == REPLY_TEXT


async def test_reject_keeps_the_record_and_replies(paused: Paused) -> None:

    """Rejecting keeps the expense, runs the safe call, saves the delete as rejected, and the agent replies."""

    await decide(paused, ApprovalChoice.reject)

    assert await rent_exists(paused.expense_id)
    assert await run_status(paused.run.run_id) == RunStatus.completed
    assert await call_statuses(paused.run.run_id) == {
        "get_missing_data": ToolCallStatus.completed,
        "delete_record": ToolCallStatus.rejected,
        }
    assert (await approval_for(paused.run.run_id)).status == ApprovalStatus.rejected
    assert await reply_text(paused.run.run_id) == REPLY_TEXT


async def test_second_click_is_refused(paused: Paused) -> None:

    """A second click on an answered card is refused and changes nothing."""

    await decide(paused, ApprovalChoice.reject)

    with pytest.raises(ApprovalNotPending):
        await decide(paused, ApprovalChoice.approve)

    assert await rent_exists(paused.expense_id)


async def test_another_user_cannot_decide(paused: Paused) -> None:

    """Someone else's click is treated as not found, and the card stays pending."""

    other_user_id = await create_user()

    try:

        with pytest.raises(ApprovalNotFound):
            await decide(paused, ApprovalChoice.approve, other_user_id)

    finally:
        await delete_user_data(other_user_id)

    assert (await approval_for(paused.run.run_id)).status == ApprovalStatus.pending


async def test_new_message_rejects_and_starts_a_new_run(paused: Paused) -> None:

    """A new message closes the paused turn without a reply, keeps the expense, then answers the new message."""

    new_run = await send(paused.user_id, paused.run.conversation_id, "hello")

    assert await rent_exists(paused.expense_id)
    assert await run_status(paused.run.run_id) == RunStatus.completed
    assert await call_statuses(paused.run.run_id) == {
        "get_missing_data": ToolCallStatus.completed,
        "delete_record": ToolCallStatus.rejected,
        }
    assert await reply_text(paused.run.run_id) == ""
    assert (await approval_for(paused.run.run_id)).decision == {"decision": "reject", "reason": "new_message"}
    assert await run_status(new_run.run_id) == RunStatus.completed
    assert await reply_text(new_run.run_id) == REPLY_TEXT


async def make_overdue(approval_id: int) -> None:

    """Move the approval's expiry to the time it was asked, so it is already overdue."""

    async with SessionLocal() as session:

        await session.execute(
            update(ToolApproval).where(ToolApproval.id == approval_id).values(expires_at=ToolApproval.requested_at)
            )

        await session.commit()


async def test_sweep_expires_and_cancels_the_run(paused: Paused) -> None:

    """The sweep expires an overdue card, runs the safe call, keeps the expense and ends the run cancelled."""

    await make_overdue(paused.approval.id)

    assert await expire_due() >= 1

    assert await rent_exists(paused.expense_id)
    assert await run_status(paused.run.run_id) == RunStatus.cancelled
    assert (await call_statuses(paused.run.run_id))["get_missing_data"] == ToolCallStatus.completed
    assert (await approval_for(paused.run.run_id)).status == ApprovalStatus.expired


async def test_late_click_expires_the_card(paused: Paused) -> None:

    """A click after the time limit is refused as expired, and the card and run close the same way the sweep would."""

    await make_overdue(paused.approval.id)

    with pytest.raises(ApprovalExpired):
        await decide(paused, ApprovalChoice.approve)

    assert await rent_exists(paused.expense_id)
    assert await run_status(paused.run.run_id) == RunStatus.cancelled
    assert (await approval_for(paused.run.run_id)).status == ApprovalStatus.expired


async def test_cancel_runs_nothing(paused: Paused) -> None:

    """Cancelling a paused run runs no tool, keeps the expense and ends the run and card as cancelled."""

    async with SessionLocal() as session:
        await RunService(session).cancel_run(paused.run.run_id, paused.user_id)

    assert await rent_exists(paused.expense_id)
    assert await run_status(paused.run.run_id) == RunStatus.cancelled
    assert await call_statuses(paused.run.run_id) == {
        "get_missing_data": ToolCallStatus.rejected,
        "delete_record": ToolCallStatus.rejected,
        }
    assert (await approval_for(paused.run.run_id)).status == ApprovalStatus.cancelled


async def test_restart_keeps_paused_runs(paused: Paused) -> None:

    """The restart cleanup leaves a paused run waiting for its card, checked in a rolled-back transaction so no other run is touched."""

    async with SessionLocal() as session:

        failed = await RunRepository(session).fail_active_runs(failure_code="test_restart")

        status = await session.scalar(select(AgentRun.status).where(AgentRun.id == paused.run.run_id))

        await session.rollback()

    assert paused.run.run_id not in failed
    assert status == RunStatus.awaiting_approval
