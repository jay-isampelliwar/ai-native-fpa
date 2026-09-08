"""The standing panel beside the conversation: what it shows, when it shows it, and what it never shows.

These moved out of the record capture tests when the skills were replaced by tools. The capture half of
that file was about a skill that no longer exists; the panel half is about behaviour nothing replaced,
so it lives here on its own.

Absence is asserted as carefully as presence. A section rendered with dashes in it teaches a person to
ignore the panel, so a section with no data must not appear at all - which makes the appearance of a
section information in itself.

The records are written through the agent's own tools rather than through a repository, which is
deliberate. It is the same path a person's conversation takes, so a change that broke the write and
left the panel reading an empty table would fail here rather than looking correct from both ends.

``test_the_panel_and_a_tool_agree_about_the_surplus`` is the one worth keeping if the file ever
shrinks. The panel and the chat compute cash flow from the same function for exactly this reason, and
a figure on screen disagreeing with the figure in the sentence beside it is the worst failure this
product has.
"""

from decimal import Decimal

import pytest

from app.agent.state import AgentContext, RunLog

pytestmark = pytest.mark.asyncio


def context_for(user_id: int) -> AgentContext:

    """Build the context the graph would hand the agent for one turn."""

    return AgentContext(user_id=user_id, conversation_id="conv_panel", correlation_id="req_panel")


async def add(user_id: int, name: str, **kwargs) -> None:

    """Write one record through the tool a conversation would have used."""

    from app.agent.tools import build_tools

    tools = {tool.name: tool for tool in build_tools(context_for(user_id), RunLog())}

    await tools[name].ainvoke(kwargs)


async def test_the_workspace_reports_what_is_missing_before_anything_exists(api_user):

    """A person who has given nothing gets a checklist, which is the panel's job before it has data."""

    from app.services.workspace import build_workspace

    readiness, sections = await build_workspace(api_user)

    assert readiness["has_any_records"] is False
    assert readiness["can_compute_cashflow"] is False
    assert set(readiness["missing"]) == {"income", "expenses", "emis", "sips"}
    assert [section.key for section in sections] == []


async def test_the_cashflow_section_appears_once_it_can_be_computed(api_user):

    """The panel gains a section the moment there is data for it, and not before."""

    from app.services.workspace import build_workspace

    await add(api_user, "add_income", label="Salary", amount="150000")
    await add(api_user, "add_expense", label="Rent", amount="30000")

    readiness, sections = await build_workspace(api_user)

    assert readiness["can_compute_cashflow"] is True
    assert "cashflow" in [section.key for section in sections]

    blocks = next(section for section in sections if section.key == "cashflow").blocks

    assert [block.type for block in blocks][:1] == ["kpi"]


async def test_a_goal_added_in_conversation_reaches_the_panel(api_user):

    """A change made in the chat is visible in the panel on its next read, with nothing to invalidate."""

    from app.services.workspace import build_workspace

    await add(api_user, "add_goal", label="Buy house", target_amount="8000000", target_year=2031)

    _, sections = await build_workspace(api_user)

    assert "goals" in [section.key for section in sections]

    table = next(
        block
        for section in sections
        if section.key == "goals"
        for block in section.blocks
        if block.type == "table"
    )

    assert table.rows[0]["goal"] == "Buy house"


async def test_the_panel_and_a_tool_agree_about_the_surplus(api_user):

    """One computation feeds both surfaces, so the panel and an answer cannot quote different figures."""

    from app.agent.tools import build_tools
    from app.services.workspace import build_workspace

    await add(api_user, "add_income", label="Salary", amount="100000")
    await add(api_user, "add_expense", label="Rent", amount="30000")

    log = RunLog()

    tools = {tool.name: tool for tool in build_tools(context_for(api_user), log)}

    answered = await tools["cashflow_summary"].ainvoke({})

    _, sections = await build_workspace(api_user)

    panel = next(
        block
        for section in sections
        if section.key == "cashflow"
        for block in section.blocks
        if block.type == "kpi" and block.label == "Free surplus"
    )

    assert answered["free_surplus"] == "70000.00"
    assert panel.value == Decimal(answered["free_surplus"])


async def test_a_retired_record_stops_counting_in_the_panel(api_user):

    """Retiring a record removes it from every future figure, which is what the panel must reflect."""

    from app.agent.tools import build_tools
    from app.services.workspace import build_workspace

    await add(api_user, "add_income", label="Salary", amount="100000")
    await add(api_user, "add_expense", label="Rent", amount="30000")

    log = RunLog()

    tools = {tool.name: tool for tool in build_tools(context_for(api_user), log)}

    listed = await tools["list_expenses"].ainvoke({})

    await tools["remove_record"].ainvoke({"kind": "expense", "record_id": listed["expenses"][0]["id"]})

    _, sections = await build_workspace(api_user)

    panel = next(
        block
        for section in sections
        if section.key == "cashflow"
        for block in section.blocks
        if block.type == "kpi" and block.label == "Free surplus"
    )

    assert panel.value == Decimal("100000.00")


async def test_the_workspace_endpoint_returns_the_same_shape(client, api_user):

    """The panel's one read is reachable and narrows to the schema the client renders."""

    response = client.get(f"/api/v1/workspace?user_id={api_user}")

    assert response.status_code == 200

    body = response.json()

    assert body["user_id"] == api_user
    assert body["readiness"]["has_any_records"] is False
    assert isinstance(body["sections"], list)


async def test_no_savings_alert_is_raised_for_someone_with_no_income(api_user):

    """Telling a person who has given nothing that they save nothing is arithmetic, not a finding."""

    from app.alerts.service import alert_service

    kinds = [alert.kind for alert in await alert_service.evaluate(api_user)]

    assert "low_savings_rate" not in kinds
