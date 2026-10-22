"""Tests that real tools return typed results through the planner's ToolNode and wrapper, on the real database."""

from collections.abc import AsyncIterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from sqlalchemy import update

from app.agent.context import PlannerContext
from app.agent.state import PlannerState
from app.agent.tools import liabilities, records
from app.agent.tools.liabilities import add_loan
from app.agent.tools.records import delete_record, list_records
from app.agent.tools.results import finish_tool_call
from app.db.enums import PhysicalAssetType
from app.db.models import Loan, PhysicalAsset
from app.db.session import SessionLocal
from tests.support import create_user, delete_user_data


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


async def no_sleep(_: float) -> None:

    """Skip the demo delay some tools still have."""


@pytest.fixture
async def user_id(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:

    """Give the test a temp user, skip the tools' demo delay, then delete everything the user owns."""

    monkeypatch.setattr(liabilities, "asyncio", SimpleNamespace(sleep=no_sleep))
    monkeypatch.setattr(records, "asyncio", SimpleNamespace(sleep=no_sleep))

    created = await create_user()

    try:
        yield created

    finally:
        await delete_user_data(created)


async def call(user_id: int, name: str, args: dict[str, Any]) -> ToolMessage:

    """Run one tool call through a ToolNode with the planner's wrapper, as the signed-in user."""

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node("tools", ToolNode([add_loan, delete_record, list_records], awrap_tool_call=finish_tool_call))
    builder.add_edge(START, "tools")

    result = await builder.compile().ainvoke(
        {"messages": [AIMessage("", tool_calls=[{"name": name, "args": args, "id": "call-1"}])]},
        context=PlannerContext(user_id=user_id),
        )

    return result["messages"][-1]


async def test_add_loan_missing_fields(user_id: int) -> None:

    """A loan with only type and lender is a validation error listing every missing detail."""

    message = await call(user_id, "add_loan", {"loan_type": "home", "lender": "HDFC"})

    assert message.status == "error"
    assert message.name == "add_loan"
    assert message.artifact["status"] == "validation_error"
    assert message.artifact["error_code"] == "missing_fields"
    assert message.artifact["data"]["missing"] == ["principal", "outstanding", "interest rate", "emi", "start date", "end date"]


async def test_add_loan_broken_rule(user_id: int) -> None:

    """An end date before the start is a validation error carrying the schema's own words."""

    message = await call(user_id, "add_loan", {**HOME_LOAN, "end_date": "2020-01-01"})

    assert message.artifact["status"] == "validation_error"
    assert message.artifact["error_code"] == "invalid_values"
    assert "End date must be after start date" in message.artifact["message"]


async def test_add_loan_saves_then_refuses_duplicate(user_id: int) -> None:

    """A full loan saves with its new id, and the same loan again is a conflict pointing at that id."""

    saved = await call(user_id, "add_loan", HOME_LOAN)

    loan_id = saved.artifact["data"]["id"]

    assert saved.status == "success"
    assert saved.artifact["data"]["lender"] == "HDFC"
    assert saved.artifact["data"]["outstanding"] == "4200000"

    duplicate = await call(user_id, "add_loan", HOME_LOAN)

    assert duplicate.artifact["status"] == "conflict"
    assert duplicate.artifact["error_code"] == "already_exists"
    assert duplicate.artifact["data"] == {"existing_id": loan_id}


async def test_list_records_returns_items(user_id: int) -> None:

    """Listing gives each saved item as data with its id, and an empty list when nothing is saved."""

    empty = await call(user_id, "list_records", {"kind": "loans"})

    saved = await call(user_id, "add_loan", HOME_LOAN)

    listed = await call(user_id, "list_records", {"kind": "loans"})

    assert empty.artifact["data"] == {"kind": "loans", "items": []}
    assert listed.artifact["data"]["items"][0]["id"] == saved.artifact["data"]["id"]
    assert listed.artifact["data"]["items"][0]["lender"] == "HDFC"


async def test_delete_missing_item_is_not_found(user_id: int) -> None:

    """Removing an id the user does not have is not found, never a crash."""

    message = await call(user_id, "delete_record", {"kind": "loans", "record_id": 999999999})

    assert message.status == "error"
    assert message.artifact["status"] == "not_found"


async def test_delete_linked_item_is_conflict(user_id: int) -> None:

    """Removing a property a loan still points at is a conflict, and the property stays saved."""

    async with SessionLocal() as session:

        flat = PhysicalAsset(
            user_id=user_id,
            asset_type=PhysicalAssetType.real_estate,
            name="Pune flat",
            current_value=Decimal("9000000"),
            )

        session.add(flat)

        await session.commit()

    await call(user_id, "add_loan", HOME_LOAN)

    async with SessionLocal() as session:

        await session.execute(update(Loan).where(Loan.user_id == user_id).values(physical_asset_id=flat.id))

        await session.commit()

    message = await call(user_id, "delete_record", {"kind": "physical_assets", "record_id": flat.id})

    assert message.artifact["status"] == "conflict"
    assert message.artifact["error_code"] == "linked_items"

    async with SessionLocal() as session:
        assert await session.get(PhysicalAsset, flat.id) is not None


async def test_delete_saved_item_returns_what_was_removed(user_id: int) -> None:

    """Removing a saved loan succeeds and returns the removed item's fields."""

    saved = await call(user_id, "add_loan", HOME_LOAN)

    loan_id = saved.artifact["data"]["id"]

    message = await call(user_id, "delete_record", {"kind": "loans", "record_id": loan_id})

    assert message.status == "success"
    assert message.artifact["data"]["removed"]["id"] == loan_id
    assert message.artifact["data"]["removed"]["lender"] == "HDFC"
