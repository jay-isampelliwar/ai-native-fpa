"""Tests for timeouts that need the real database: the statement timeout, a write that times out after it committed, and the turn budget."""

import asyncio
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import graph as planner
from app.agent.checkpointer import open_checkpointer
from app.agent.context import PlannerContext
from app.agent.state import PlannerState
from app.agent.tools import policies
from app.agent.tools.limits import tool_session
from app.agent.tools.operations import run_write
from app.agent.tools.results import ToolResult, checked, to_message
from app.agent.tools.wrapper import finish_tool_call
from app.core.config import get_settings
from app.db.enums import LoanType, RunStatus
from app.db.models import AgentRun, Loan
from app.db.session import SessionLocal
from app.features.runs.worker import execute_run
from app.services import llm
from tests.support import SeededRun, create_user, delete_user_data, seed_run


tries: list[int] = []


@pytest.fixture
async def seeded() -> AsyncIterator[SeededRun]:

    """Give the test a temp user with a conversation and a queued run, then delete everything the user owns."""

    user_id = await create_user()

    try:
        yield await seed_run(user_id)

    finally:
        await delete_user_data(user_id)


async def test_statement_timeout_stops_a_slow_query(monkeypatch: pytest.MonkeyPatch) -> None:

    """Postgres itself stops a query that runs longer than the tool session's statement timeout."""

    monkeypatch.setattr(get_settings(), "DB_STATEMENT_TIMEOUT_MS", 200)

    with pytest.raises(OperationalError, match="statement timeout"):

        async with tool_session(PlannerContext(user_id=1)) as session:
            await session.execute(text("SELECT pg_sleep(2)"))


@tool
async def save_then_hang(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Save a loan through the guard, then hang on the first try only, as if the answer was lost after the commit."""

    tries.append(len(tries) + 1)

    async def save(session: AsyncSession) -> ToolResult:

        """Add one loan in the guard's session."""

        loan = Loan(
            user_id=runtime.context.user_id,
            loan_type=LoanType.home,
            lender="HDFC",
            principal=Decimal("5000000"),
            outstanding=Decimal("4200000"),
            interest_rate=Decimal("8.5"),
            emi=Decimal("43391"),
            start_date=date(2022, 4, 1),
            end_date=date(2042, 3, 31),
            )

        session.add(loan)

        await session.flush()

        return checked("Saved loan.", {"id": loan.id})

    result = await run_write(runtime, save)

    if len(tries) == 1:
        await asyncio.sleep(1)

    return to_message(result, runtime.tool_call_id)


async def test_write_that_times_out_after_commit_is_saved_once(
    seeded: SeededRun,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """The retry of a write that committed and then timed out gives back the same loan instead of a second one."""

    monkeypatch.setattr(get_settings(), "TOOL_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(get_settings(), "TOOL_RETRY_BASE_SECONDS", 0.01)
    monkeypatch.setattr(get_settings(), "MIN_RETRY_SECONDS", 0)
    monkeypatch.setitem(policies.TOOL_POLICIES, "save_then_hang", policies.WRITE)

    tries.clear()

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node("tools", ToolNode([save_then_hang], awrap_tool_call=finish_tool_call))
    builder.add_edge(START, "tools")

    result = await builder.compile().ainvoke(
        {"messages": [AIMessage("", tool_calls=[{"name": "save_then_hang", "args": {}, "id": "call_A"}])]},
        context=PlannerContext(user_id=seeded.user_id, conversation_id=seeded.conversation_id, run_id=seeded.run_id),
        )

    async with SessionLocal() as session:
        loans = await session.scalar(select(func.count()).select_from(Loan).where(Loan.user_id == seeded.user_id))

    assert tries == [1, 2]
    assert result["messages"][-1].artifact["status"] == "success"
    assert loans == 1


class SlowModel:

    """A model that takes longer to answer than the whole turn may."""

    async def astream(self, messages: list) -> AsyncIterator[AIMessageChunk]:

        """Wait past the turn budget, then answer."""

        await asyncio.sleep(2)

        yield AIMessageChunk("Too late.")


async def test_turn_that_runs_out_of_time_fails(seeded: SeededRun, monkeypatch: pytest.MonkeyPatch) -> None:

    """A turn longer than its budget ends failed with turn_timeout, whatever was still running."""

    monkeypatch.setattr(get_settings(), "TURN_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(llm.llm_service, "with_tools", lambda tools, model=None, max_tokens=None: SlowModel())

    async with open_checkpointer() as checkpointer:

        planner.planner_graph = planner.build_planner_graph(checkpointer)

        try:
            await execute_run(seeded.run_id, seeded.conversation_id, seeded.user_id, seeded.assistant_message_id, "hello")

        finally:
            await checkpointer.adelete_thread(str(seeded.conversation_id))

    async with SessionLocal() as session:
        run = await session.get(AgentRun, seeded.run_id)

    assert run.status == RunStatus.failed
    assert run.failure_code == "turn_timeout"
