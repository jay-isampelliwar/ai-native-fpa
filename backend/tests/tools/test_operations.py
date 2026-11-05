"""Tests for the idempotency guard: a write runs once per tool call, inside a real conversation on the real database."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from sqlalchemy import func, select

from app.agent.context import PlannerContext
from app.agent.state import PlannerState
from app.agent.tools.liabilities import add_loan
from app.agent.tools.records import delete_record
from app.agent.tools.wrapper import finish_tool_call
from app.db.models import Loan, ToolOperation
from app.db.session import SessionLocal
from app.features.operations.repository import OperationRepository
from tests.support import SeededRun, create_user, delete_user_data, seed_run


HOME_LOAN = {
    "loan_type": "home",
    "lender": "HDFC",
    "principal": 5000000,
    "outstanding": 4200000,
    "interest_rate": 8.5,
    "emi": 43391,
    "start_date": "2022-04-01",
    "end_date": "2042-03-31",
    }

SECOND_LOAN = {**HOME_LOAN, "principal": 3000000, "outstanding": 2500000}



@pytest.fixture
async def seeded() -> AsyncIterator[SeededRun]:

    """Give the test a temp user with a conversation and run, then delete everything the user owns."""


    user_id = await create_user()

    try:
        yield await seed_run(user_id)

    finally:
        await delete_user_data(user_id)


async def call(
    seeded: SeededRun,
    call_id: str,
    name: str,
    args: dict[str, Any],
    in_conversation: bool = True,
    ) -> ToolMessage:

    """Run one tool call with this id through the planner's ToolNode, inside the seeded conversation and run."""

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node("tools", ToolNode([add_loan, delete_record], awrap_tool_call=finish_tool_call))
    builder.add_edge(START, "tools")

    context = PlannerContext(
        user_id=seeded.user_id,
        conversation_id=seeded.conversation_id if in_conversation else None,
        run_id=seeded.run_id if in_conversation else None,
        )

    result = await builder.compile().ainvoke(
        {"messages": [AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id}])]},
        context=context,
        )

    return result["messages"][-1]


async def counts(user_id: int) -> tuple[int, int]:

    """Return how many loans and how many saved operations the user has."""

    async with SessionLocal() as session:

        loans = await session.scalar(select(func.count()).select_from(Loan).where(Loan.user_id == user_id))
        operations = await session.scalar(
            select(func.count()).select_from(ToolOperation).where(ToolOperation.user_id == user_id)
            )

    return loans, operations


async def test_first_call_saves_the_write_and_its_operation(seeded: SeededRun) -> None:

    """A new call saves the loan and one operation row holding the same result, for this conversation and run."""

    message = await call(seeded, "call_A", "add_loan", HOME_LOAN)

    async with SessionLocal() as session:
        saved = await OperationRepository(session).find(seeded.conversation_id, "call_A")

    assert message.artifact["status"] == "success"
    assert await counts(seeded.user_id) == (1, 1)
    assert saved.tool_name == "add_loan"
    assert saved.run_id == seeded.run_id
    assert saved.result == message.artifact


async def test_replayed_call_returns_the_saved_result(seeded: SeededRun) -> None:

    """The same call with the same arguments gives back the first loan's id and saves nothing new."""

    first = await call(seeded, "call_A", "add_loan", HOME_LOAN)
    replay = await call(seeded, "call_A", "add_loan", HOME_LOAN)

    assert replay.status == "success"
    assert replay.artifact == first.artifact
    assert await counts(seeded.user_id) == (1, 1)


async def test_replay_with_changed_arguments_is_refused(seeded: SeededRun) -> None:

    """The same call id with different arguments is a conflict, and nothing new is saved."""

    await call(seeded, "call_A", "add_loan", HOME_LOAN)

    replay = await call(seeded, "call_A", "add_loan", SECOND_LOAN)

    assert replay.status == "error"
    assert replay.artifact["status"] == "conflict"
    assert replay.artifact["error_code"] == "idempotency_mismatch"
    assert await counts(seeded.user_id) == (1, 1)


async def test_new_call_saves_a_second_loan_from_the_same_lender(seeded: SeededRun) -> None:

    """A new call for a second HDFC home loan saves it as its own loan."""

    first = await call(seeded, "call_A", "add_loan", HOME_LOAN)
    second = await call(seeded, "call_B", "add_loan", SECOND_LOAN)

    assert second.artifact["status"] == "success"
    assert second.artifact["data"]["id"] != first.artifact["data"]["id"]
    assert await counts(seeded.user_id) == (2, 2)


async def test_failed_write_saves_no_operation(seeded: SeededRun) -> None:

    """A refused write saves no operation, so the same call can still succeed once the problem is fixed."""

    missing = await call(seeded, "call_A", "add_loan", {"loan_type": "home", "lender": "HDFC"})
    not_found = await call(seeded, "call_B", "delete_record", {"kind": "loans", "record_id": 999999999})

    assert missing.artifact["status"] == "validation_error"
    assert not_found.artifact["status"] == "not_found"
    assert await counts(seeded.user_id) == (0, 0)


async def test_write_and_operation_commit_together(seeded: SeededRun, monkeypatch: pytest.MonkeyPatch) -> None:

    """When saving the operation fails, the call comes back failed and the loan is rolled back with it, so a loan never exists without its operation."""

    def broken_add(self: OperationRepository, *args: Any) -> None:

        """Fail the way a lost connection would, after the loan was added to the session."""

        raise RuntimeError("operation could not be saved")

    monkeypatch.setattr(OperationRepository, "add", broken_add)

    message = await call(seeded, "call_A", "add_loan", HOME_LOAN)

    assert message.status == "error"
    assert '"tool_failed"' in message.content
    assert await counts(seeded.user_id) == (0, 0)


async def test_delete_replay_does_not_fail(seeded: SeededRun) -> None:

    """Replaying a delete gives back the first "removed" result instead of a not found."""

    saved = await call(seeded, "call_A", "add_loan", HOME_LOAN)

    args = {"kind": "loans", "record_id": saved.artifact["data"]["id"]}

    first = await call(seeded, "call_B", "delete_record", args)
    replay = await call(seeded, "call_B", "delete_record", args)

    assert first.artifact["status"] == "success"
    assert replay.artifact == first.artifact


async def test_outside_a_conversation_the_write_still_runs(seeded: SeededRun) -> None:

    """With no conversation there is nothing to replay, so the loan saves and no operation is kept."""

    message = await call(seeded, "call_A", "add_loan", HOME_LOAN, in_conversation=False)

    assert message.artifact["status"] == "success"
    assert await counts(seeded.user_id) == (1, 0)
