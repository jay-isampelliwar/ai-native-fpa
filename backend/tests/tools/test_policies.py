"""Tests for the tool risk policy, the update preview and the owner check inside the UPDATE and DELETE themselves."""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.approval import change_preview, preview_for
from app.agent.tools import ALL_TOOLS
from app.agent.tools.policies import TOOL_POLICIES, Risk, needs_approval
from app.agent.tools.wrapper import finish_tool_call
from app.db.enums import ExpenseCategory
from app.db.models import Expense
from app.db.session import SessionLocal
from app.features.cash_flow.repository import CashFlowRepository
from tests.support import create_user, delete_user_data


def test_every_tool_has_a_policy() -> None:

    """A tool cannot be added to the planner without a risk level, and the table names no tool that does not exist."""

    names = {planner_tool.name for planner_tool in ALL_TOOLS}

    assert names == set(TOOL_POLICIES)


def test_only_update_and_delete_need_approval() -> None:

    """Approval is asked for changing and removing saved items, and for nothing else."""

    approved = {name for name in TOOL_POLICIES if needs_approval(name)}

    assert approved == {"update_record", "delete_record"}
    assert TOOL_POLICIES["delete_record"].risk == Risk.destructive
    assert TOOL_POLICIES["update_record"].risk == Risk.sensitive


def test_read_tools_are_read() -> None:

    """The three tools that only read are marked read."""

    reads = {name for name, policy in TOOL_POLICIES.items() if policy.risk == Risk.read}

    assert reads == {"list_records", "get_missing_data", "check_goal_progress"}


@tool
async def not_in_policy(runtime: ToolRuntime) -> str:

    """A tool the server never gave a policy."""

    return "this must never run"


async def test_tool_without_policy_is_refused() -> None:

    """A tool with no policy is answered as not allowed and never runs."""

    builder = StateGraph(MessagesState)

    builder.add_node("tools", ToolNode([not_in_policy], awrap_tool_call=finish_tool_call))
    builder.add_edge(START, "tools")

    calls = [{"name": "not_in_policy", "args": {}, "id": "call-1"}]

    result = await builder.compile().ainvoke({"messages": [AIMessage("", tool_calls=calls)]})

    message: ToolMessage = result["messages"][-1]

    assert message.status == "error"
    assert message.name == "not_in_policy"
    assert message.artifact["status"] == "not_allowed"
    assert "never run" not in str(message.content)


@pytest.fixture
async def rent() -> AsyncIterator[tuple[int, int]]:

    """Give the test a temp user with one saved rent expense, then delete everything the user owns."""

    user_id = await create_user()

    try:

        async with SessionLocal() as session:

            expense = Expense(user_id=user_id, category=ExpenseCategory.rent, name="Rent", amount=Decimal("20000"))

            session.add(expense)

            await session.commit()

        yield user_id, expense.id

    finally:
        await delete_user_data(user_id)


def update_call(expense_id: int, changes: dict) -> dict:

    """An update_record call for the rent expense."""

    return {"name": "update_record", "args": {"kind": "expenses", "record_id": expense_id, "changes": changes}, "id": "u1"}


async def test_change_preview_shows_old_and_new(rent: tuple[int, int]) -> None:

    """The update card shows the saved amount next to the new one."""

    user_id, expense_id = rent

    preview = await change_preview(update_call(expense_id, {"amount": 25000}), user_id)

    assert preview["action"] == "change"
    assert preview["title"] == "Change this expense?"
    assert preview["fields"] == [{"name": "amount", "old": "20000", "new": "25000"}]


async def test_change_preview_skips_bad_updates(rent: tuple[int, int]) -> None:

    """No card for a field that cannot be changed, an empty change, or someone else's item, since the tool refuses those itself."""

    user_id, expense_id = rent

    assert await change_preview(update_call(expense_id, {"user_id": 1}), user_id) is None
    assert await change_preview(update_call(expense_id, {}), user_id) is None
    assert await change_preview(update_call(expense_id, {"amount": 1}), user_id + 1_000_000) is None


async def test_approval_tool_without_its_own_preview_still_pauses() -> None:

    """A tool that needs approval but has no preview builder gets a plain card instead of running unasked."""

    preview = await preview_for({"name": "set_tax_profile", "args": {"regime": "new"}, "id": "t1"}, user_id=1)

    assert preview["action"] == "run"
    assert preview["fields"] == [{"name": "regime", "value": "new"}]


async def test_update_and_delete_refuse_another_users_row(rent: tuple[int, int]) -> None:

    """Another user's id in the UPDATE or DELETE changes nothing, because the owner is part of the query."""

    user_id, expense_id = rent

    other_user_id = await create_user()

    try:

        async with SessionLocal() as session:

            repo = CashFlowRepository(session)

            updated = await repo.update_for_user(Expense, expense_id, other_user_id, {"amount": Decimal("1")})
            deleted = await repo.delete_for_user(Expense, expense_id, other_user_id)

            await session.commit()

    finally:
        await delete_user_data(other_user_id)

    async with SessionLocal() as session:
        expense = await session.get(Expense, expense_id)

    assert updated is None
    assert deleted is False
    assert expense.amount == Decimal("20000")


async def test_update_and_delete_work_for_the_owner(rent: tuple[int, int]) -> None:

    """The owner's UPDATE returns the changed row, and the owner's DELETE removes it."""

    user_id, expense_id = rent

    async with SessionLocal() as session:

        repo = CashFlowRepository(session)

        updated = await repo.update_for_user(Expense, expense_id, user_id, {"amount": Decimal("25000")})

        await session.commit()

    assert updated.amount == Decimal("25000")

    async with SessionLocal() as session:

        deleted = await CashFlowRepository(session).delete_for_user(Expense, expense_id, user_id)

        await session.commit()

    async with SessionLocal() as session:
        assert await session.get(Expense, expense_id) is None

    assert deleted is True
