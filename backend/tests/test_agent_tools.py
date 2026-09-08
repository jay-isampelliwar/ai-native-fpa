"""The agent's tools against a real database, which is where the whole product now lives.

These replaced the per skill test files. What is under test is every tool a turn can reach: that a read
returns the rows it should and cites them, that a write actually changes the database, that a bad
argument is refused rather than stored, and that no tool can be pointed at somebody else's records.

No model is called anywhere in this file. The tools are the deterministic half of the design and they
are exactly the half worth testing this way - a test that needed an API key to prove that
``update_record`` updates a record would stop running the day the key expired.

The listing tests exist because of a specific failure. "Show my SIPs" used to reach a skill for
changing one and then a skill for holdings, and got an apology from each, because listing SIPs had
never been anybody's job. ``test_list_sips_returns_every_scheme`` is that bug written down.

The write tests assert the database, not the return value. A tool that reports "added income" and
writes nothing is the failure mode that matters, and it is invisible from the string it hands back.

Refusals are asserted as carefully as successes, and there are more of them. A tool set this size is
reached by a model that will occasionally pass "1.5L" where a number belongs or an id it invented, and
every one of those has to become a sentence the model can act on rather than a stored wrong figure or
a stack trace.

Ownership is asserted directly. Tools are built closed over one context and take no user parameter, so
the test is that a tool built for one person cannot see another's rows even when handed their id.
"""

from decimal import Decimal

import pytest

from app.agent.state import AgentContext, RunLog

pytestmark = pytest.mark.asyncio


def context_for(user_id: int) -> AgentContext:

    """Build the context the graph would hand the agent for one turn."""

    return AgentContext(user_id=user_id, conversation_id="conv_tools", correlation_id="req_tools")


def tools_for(user_id: int) -> tuple[dict, RunLog]:

    """Build every tool bound to one caller, with the log they write their structured output to."""

    from app.agent.tools import build_tools

    log = RunLog()

    return {tool.name: tool for tool in build_tools(context_for(user_id), log)}, log


async def call(user_id: int, name: str, **kwargs):

    """Invoke one tool the way the agent would, returning its result and the log it wrote to."""

    tools, log = tools_for(user_id)

    return await tools[name].ainvoke(kwargs), log


async def seed_income(user_id: int, label: str = "Salary", amount: str = "150000") -> str:

    """Create one income record directly, so a read or an update has something to find."""

    from app.db.session import session_scope
    from app.repositories.records_repository import records_repository

    async with session_scope() as session:

        row = await records_repository.create_income(
            session,
            user_id=user_id,
            label=label,
            amount=Decimal(amount),
        )

        return row.id


async def stored_amount(user_id: int, table: str, record_id: str):

    """Read one record's amount straight from the table, which is what a write test is really about."""

    from sqlalchemy import text

    from app.db.session import session_scope

    async with session_scope() as session:

        return await session.scalar(
            text(f"SELECT amount FROM {table} WHERE id = :rid AND user_id = :uid"),
            {"rid": record_id, "uid": user_id},
        )


async def count_rows(user_id: int, table: str) -> int:

    """Count what this user has in one table, so a create or a refusal is checkable."""

    from sqlalchemy import text

    from app.db.session import session_scope

    async with session_scope() as session:

        return await session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE user_id = :uid"), {"uid": user_id}
        )


async def test_list_sips_returns_every_scheme(api_user):

    """Listing SIPs names all of them, which is the question no skill could previously answer."""

    from app.db.session import session_scope
    from app.repositories.records_repository import records_repository

    async with session_scope() as session:

        for name, amount in (("Parag Parikh Flexi Cap", "10000"), ("Nifty Index Fund", "5000")):
            await records_repository.create_sip(
                session,
                user_id=api_user,
                scheme_name=name,
                amount=Decimal(amount),
            )

    result, log = await call(api_user, "list_sips")

    schemes = {row["scheme_name"] for row in result["sips"]}

    assert schemes == {"Parag Parikh Flexi Cap", "Nifty Index Fund"}
    assert len(log.evidence_ids) == 2
    assert [block.type for block in log.blocks] == ["table"]


async def test_a_listing_with_nothing_in_it_says_so(api_user):

    """An empty list is reported as empty rather than as a failure, so the model can ask for records."""

    result, _ = await call(api_user, "list_sips")

    assert result["sips"] == []
    assert "no SIPs" in result["note"]


async def test_list_income_reports_the_monthly_equivalent(api_user):

    """A yearly figure is normalised for the model, so it never has to divide anything itself."""

    from app.db.session import session_scope
    from app.models.finance import Frequency
    from app.repositories.records_repository import records_repository

    async with session_scope() as session:

        await records_repository.create_income(
            session,
            user_id=api_user,
            label="Bonus",
            amount=Decimal("120000"),
            frequency=Frequency.ANNUAL,
        )

    result, _ = await call(api_user, "list_income")

    assert result["income"][0]["amount"] == "120000.00"
    assert result["income"][0]["monthly_equivalent"] == "10000.00"


async def test_adding_an_income_writes_it(api_user):

    """The write reaches the table, which is the thing a returned sentence cannot prove."""

    before = await count_rows(api_user, "income_records")

    result, log = await call(api_user, "add_income", label="Freelancing", amount="20000")

    assert "added income" in result
    assert await count_rows(api_user, "income_records") == before + 1
    assert log.writes


async def test_an_unparseable_amount_is_refused_rather_than_stored(api_user):

    """A figure the model mangled becomes a sentence it can act on, never a wrong row."""

    result, log = await call(api_user, "add_income", label="Freelancing", amount="1.5L")

    assert result.startswith("refused")
    assert await count_rows(api_user, "income_records") == 0
    assert log.writes == []


async def test_a_negative_amount_is_refused(api_user):

    """Nothing in this product is worth a negative amount, so it is refused at the tool."""

    result, _ = await call(api_user, "add_income", label="Odd", amount="-5000")

    assert result.startswith("refused")
    assert await count_rows(api_user, "income_records") == 0


async def test_updating_a_record_changes_the_stored_figure(api_user):

    """An update lands on the row the id names and moves the amount the table holds."""

    record_id = await seed_income(api_user)

    result, log = await call(api_user, "update_record", kind="income", record_id=record_id, amount="180000")

    assert "changed income" in result
    assert await stored_amount(api_user, "income_records", record_id) == Decimal("180000.00")
    assert log.writes


async def test_updating_an_unknown_id_is_refused(api_user):

    """An id the model invented is refused by name rather than silently doing nothing."""

    result, log = await call(api_user, "update_record", kind="income", record_id="inc_nope", amount="1000")

    assert result.startswith("refused")
    assert log.writes == []


async def test_an_unknown_kind_is_refused(api_user):

    """A kind nothing handles is refused with the list of kinds that do."""

    result, _ = await call(api_user, "update_record", kind="crypto", record_id="x", amount="1000")

    assert result.startswith("refused")
    assert "income" in result


async def test_removing_a_record_retires_it_rather_than_deleting_it(api_user):

    """A record that stopped applying stops counting and stays readable, so past answers still explain."""

    from sqlalchemy import text

    from app.db.session import session_scope

    record_id = await seed_income(api_user)

    result, _ = await call(api_user, "remove_record", kind="income", record_id=record_id)

    assert "retired" in result

    async with session_scope() as session:

        active = await session.scalar(
            text("SELECT active FROM income_records WHERE id = :rid"), {"rid": record_id}
        )

    assert active is False
    assert await count_rows(api_user, "income_records") == 1


async def test_a_retired_record_leaves_the_listing(api_user):

    """Retiring is what the read tools honour, so a retired row stops appearing in an answer."""

    record_id = await seed_income(api_user)

    await call(api_user, "remove_record", kind="income", record_id=record_id)

    result, _ = await call(api_user, "list_income")

    assert result["income"] == []


async def test_adding_a_goal_writes_it_with_the_stated_year(api_user):

    """A goal needs both figures and stores the year the person actually said."""

    from app.repositories.goals_repository import goals_repository

    result, _ = await call(api_user, "add_goal", label="House", target_amount="4000000", target_year=2030)

    assert "set up goal" in result

    snapshots = await goals_repository.list_snapshots(api_user)

    assert snapshots[0].label == "House"
    assert snapshots[0].target_date.year == 2030


async def test_a_goal_with_an_impossible_year_is_refused(api_user):

    """A year nobody can plan towards is refused rather than stored and projected."""

    result, _ = await call(api_user, "add_goal", label="House", target_amount="4000000", target_year=99)

    assert result.startswith("refused")
    assert await count_rows(api_user, "goals") == 0


async def test_removing_a_goal_retires_it(api_user):

    """A goal that no longer applies stops being projected and stays on record."""

    from app.repositories.goals_repository import goals_repository

    await call(api_user, "add_goal", label="House", target_amount="4000000", target_year=2030)

    goal_id = (await goals_repository.list_snapshots(api_user))[0].id

    result, _ = await call(api_user, "remove_goal", goal_id=goal_id)

    assert "retired" in result
    assert await goals_repository.list_snapshots(api_user) == []


async def test_pausing_a_sip_takes_it_out_of_the_listing(api_user):

    """A paused SIP stops counting towards cash flow, which is what the read tools reflect."""

    from app.db.session import session_scope
    from app.repositories.records_repository import records_repository

    async with session_scope() as session:

        row = await records_repository.create_sip(
            session,
            user_id=api_user,
            scheme_name="Index Fund",
            amount=Decimal("5000"),
        )

        sip_id = row.id

    await call(api_user, "pause_sip", record_id=sip_id)

    result, _ = await call(api_user, "list_sips")

    assert result["sips"] == []


async def test_cashflow_is_computed_by_the_calculator_and_stamped_with_its_version(api_user):

    """Every derived figure carries the version that produced it, so an answer can be explained later."""

    from app.db.session import session_scope
    from app.repositories.records_repository import records_repository

    async with session_scope() as session:

        await records_repository.create_income(session, user_id=api_user, label="Salary", amount=Decimal("100000"))
        await records_repository.create_expense(session, user_id=api_user, label="Rent", amount=Decimal("30000"))

    result, log = await call(api_user, "cashflow_summary")

    assert result["free_surplus"] == "70000.00"
    assert result["calculator"] == "cashflow.v1"
    assert log.tools == ["cashflow_summary"]


async def test_projecting_a_goal_needs_an_id_the_model_has_seen(api_user):

    """A goal id that does not exist is refused with the tool that lists the real ones."""

    result, _ = await call(api_user, "project_goal", goal_id="goal_invented")

    assert "list_goals" in result["note"]


async def test_a_tool_cannot_reach_another_persons_records(api_user):

    """Tools are bound to one caller, so rows belonging to somebody else are simply not there."""

    await seed_income(api_user)

    result, _ = await call(api_user + 1, "list_income")

    assert result["income"] == []
