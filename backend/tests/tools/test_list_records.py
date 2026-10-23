"""Tests for list_records paging, filters, sort and chosen fields, on the real database."""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.context import PlannerContext
from app.agent.state import PlannerState
from app.agent.tools.records import list_records
from app.agent.tools.wrapper import finish_tool_call
from app.db.enums import ExpenseCategory
from app.db.models import Expense
from app.db.session import SessionLocal
from tests.support import create_user, delete_user_data


AMOUNTS = [5000, 25000, 1500, 12000, 800]


@pytest.fixture
async def user_id() -> AsyncIterator[int]:

    """Give the test a temp user with five expenses, one of them rent, then delete everything the user owns."""

    created = await create_user()

    try:

        async with SessionLocal() as session:

            for index, amount in enumerate(AMOUNTS):

                category = ExpenseCategory.rent if amount == 25000 else ExpenseCategory.groceries

                session.add(Expense(user_id=created, category=category, name=f"Expense {index}", amount=Decimal(amount)))

            await session.commit()

        yield created

    finally:
        await delete_user_data(created)


async def listed(user_id: int, **args: Any) -> ToolMessage:

    """Call list_records for expenses with these options, through the planner's ToolNode and wrapper."""

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node("tools", ToolNode([list_records], awrap_tool_call=finish_tool_call))
    builder.add_edge(START, "tools")

    calls = [{"name": "list_records", "args": {"kind": "expenses", **args}, "id": "call-1"}]

    result = await builder.compile().ainvoke(
        {"messages": [AIMessage("", tool_calls=calls)]},
        context=PlannerContext(user_id=user_id),
        )

    return result["messages"][-1]


def amounts(message: ToolMessage) -> list[str]:

    """The amounts of the listed items, in the order they came back."""

    return [item["amount"] for item in message.artifact["data"]["items"]]


async def test_pages_follow_the_cursor(user_id: int) -> None:

    """Two items a page gives three pages, each pointing at the next, and the last pointing nowhere."""

    first = await listed(user_id, page_size=2)
    second = await listed(user_id, page_size=2, cursor=first.artifact["data"]["next_cursor"])
    last = await listed(user_id, page_size=2, cursor=second.artifact["data"]["next_cursor"])

    assert first.artifact["data"]["total"] == 5
    assert first.artifact["message"] == "Showing 2 of 5 expenses."
    assert first.artifact["data"]["next_cursor"] == 2
    assert second.artifact["data"]["next_cursor"] == 4
    assert last.artifact["data"]["next_cursor"] is None
    assert amounts(first) + amounts(second) + amounts(last) == ["5000", "25000", "1500", "12000", "800"]


async def test_sort_largest_first(user_id: int) -> None:

    """A minus in front of the field sorts largest first."""

    message = await listed(user_id, sort="-amount", page_size=3)

    assert amounts(message) == ["25000", "12000", "5000"]


async def test_filter_turns_values_into_the_field_type(user_id: int) -> None:

    """A filter matches by the field's own type, so a category given as text and an amount given as text both work."""

    by_category = await listed(user_id, filters={"category": "rent"})
    by_amount = await listed(user_id, filters={"amount": "1500"})

    assert amounts(by_category) == ["25000"]
    assert amounts(by_amount) == ["1500"]


async def test_no_match_says_so(user_id: int) -> None:

    """A filter that matches nothing says so, instead of saying nothing is saved."""

    message = await listed(user_id, filters={"name": "Nothing like this"})

    assert message.artifact["message"] == "No expenses match these filters."
    assert message.artifact["data"]["total"] == 0


async def test_chosen_fields_keep_the_answer_small(user_id: int) -> None:

    """Asking for some fields returns only those, always with the id."""

    message = await listed(user_id, fields=["amount"], page_size=1)

    assert list(message.artifact["data"]["items"][0]) == ["id", "amount"]


async def test_unknown_field_is_a_validation_error(user_id: int) -> None:

    """A filter, sort or field the item does not have is refused, naming the fields that can be used."""

    bad_filter = await listed(user_id, filters={"user_id": 1})
    bad_sort = await listed(user_id, sort="-salary")
    bad_fields = await listed(user_id, fields=["password"])
    bad_value = await listed(user_id, filters={"amount": "a lot"})

    for message in (bad_filter, bad_sort, bad_fields, bad_value):
        assert message.artifact["status"] == "validation_error"

    assert "Fields you can use" in bad_filter.artifact["message"]


async def test_page_size_is_kept_within_bounds(user_id: int) -> None:

    """A page size over the maximum is cut down to it, and below one is raised to one."""

    too_big = await listed(user_id, page_size=500)
    too_small = await listed(user_id, page_size=0)

    assert len(too_big.artifact["data"]["items"]) == 5
    assert len(too_small.artifact["data"]["items"]) == 1
