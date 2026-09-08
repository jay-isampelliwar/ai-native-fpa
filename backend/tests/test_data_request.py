"""What a person with no records is shown, which is now a set of questions rather than a paragraph.

The failure being tested for is one a person meets on their first message and never mentions. Every
answer the planner can give is computed from records, someone new has none, and both skills that get
asked first used to say so in prose: orientation listed four things to send in one sentence, and the
cash flow summary refused and named two of them. Neither gave anything to act on, so the questions
now come one per record type with example answers, and both skills ask in the same words because they
read the same module.

The ask is asserted where it is made rather than everywhere it could be. It rides on the
``cashflow_summary`` tool, which is the one that actually needed a figure it did not have; a greeting
gets a sentence from the agent and no checklist, because somebody saying hello is not asking for one.

The tests use fake repositories rather than the database. What is under test is what gets asked for a
given set of counts, and every count worth asking about can be handed over directly - a test that
needs rows inserted to prove that a person with no rows is asked four questions is a slower test of
something narrower.

The examples are asserted to be answers rather than illustrations. An EMI example with no tenure in
it would be refused by ``add_emi`` for missing the one field a liability cannot be stored without, so
an example that reads well and cannot be sent is worse than no example - it teaches a sentence that
fails.

The tool is reached through a fake repository rather than the database, which is what the injection
point in ``build_analysis_tools`` is for. What is under test is which questions a given set of counts
produces, and handing the counts over directly is a faster test of exactly that.
"""

import pytest

from app.agent.context import AgentContext, RunLog
from app.models.finance import CashflowRecords, ExpenseRecord, IncomeRecord

pytestmark = pytest.mark.asyncio

CONTEXT = AgentContext(user_id=1, conversation_id="conv_ask", correlation_id="req_ask")


class FakeRepository:

    """A repository holding exactly the records a test hands it, and nothing else."""

    def __init__(self, records: CashflowRecords) -> None:

        """Keep the bundle every read should return."""

        self._records = records

    async def get_cashflow_records(self, user_id: int) -> CashflowRecords:

        """Return the prepared bundle, ignoring the user since there is only one."""

        return self._records


def nothing() -> CashflowRecords:

    """Build the empty bundle a person has before their first answer."""

    return CashflowRecords()


def salary_only() -> CashflowRecords:

    """Build the bundle of someone who answered the first question and stopped."""

    return CashflowRecords(
        income=[IncomeRecord(id="inc_1", user_id=1, label="Salary", amount="100000")]
    )


def only(blocks, kind: str):

    """Pick the blocks of one type out of a result, which is how each assertion finds its subject."""

    return [block for block in blocks if block.type == kind]


async def summarise(monkeypatch, records: CashflowRecords) -> tuple[dict, RunLog]:

    """Run the cash flow tool against a fixed set of records, returning its result and its log."""

    from app.agent.tools import analysis

    monkeypatch.setattr(analysis, "get_cashflow_repository", lambda: FakeRepository(records))

    log = RunLog()

    tools = {tool.name: tool for tool in analysis.build_analysis_tools(CONTEXT, log)}

    return await tools["cashflow_summary"].ainvoke({}), log


async def test_someone_with_no_records_is_asked_for_all_four():

    """The ask is four answerable questions, in the order that unlocks the most."""

    from app.ui.asks import data_request

    ask = data_request({"income": 0, "expenses": 0, "emis": 0, "sips": 0})

    assert [item.label for item in ask.items] == ["Income", "Regular expenses", "Loan EMIs", "SIPs"]

    assert all(item.examples for item in ask.items)

    assert "attach a bank or holdings statement" in ask.caption


async def test_a_record_type_already_given_is_not_asked_for_again():

    """Someone who has answered one question is asked the remaining three and not the first."""

    from app.ui.asks import data_request

    asked = [item.label for item in data_request({"income": 1}).items]

    assert asked == ["Regular expenses", "Loan EMIs", "SIPs"]

    assert "Income" not in asked


async def test_a_complete_set_of_records_is_asked_nothing():

    """The ask disappears once there is nothing left to ask for, rather than becoming an empty card."""

    from app.ui.asks import data_request

    assert data_request({"income": 1, "expenses": 3, "emis": 1, "sips": 2}) is None


async def test_the_cashflow_tool_asks_the_same_questions_when_it_has_nothing(monkeypatch):

    """A money question from someone with no records produces the questions, not just a no."""

    result, log = await summarise(monkeypatch, nothing())

    assert "no income or expense records" in result["note"]

    asks = only(log.blocks, "prompt")

    assert [item.label for item in asks[0].items] == ["Income", "Regular expenses", "Loan EMIs", "SIPs"]


async def test_a_thin_answer_carries_the_ask_for_what_is_missing(monkeypatch):

    """A figure computed from one record still asks for the rest, since a 100% savings rate is not an insight."""

    result, log = await summarise(monkeypatch, salary_only())

    assert result["total_income"] == "100000.00"

    assert [item.label for item in only(log.blocks, "prompt")[0].items] == [
        "Regular expenses",
        "Loan EMIs",
        "SIPs",
    ]

    assert log.blocks[-1].type == "prompt"


async def test_a_complete_answer_carries_no_ask(monkeypatch):

    """Nothing is asked of someone whose records cover every input the calculator takes."""

    records = CashflowRecords(
        income=[IncomeRecord(id="inc_1", user_id=1, label="Salary", amount="100000")],
        expenses=[ExpenseRecord(id="exp_1", user_id=1, label="Rent", amount="30000")],
        emis=[],
        sips=[],
    )

    _, log = await summarise(monkeypatch, records)

    assert [item.label for item in only(log.blocks, "prompt")[0].items] == ["Loan EMIs", "SIPs"]


async def test_the_tool_states_the_calculator_behind_every_figure(monkeypatch):

    """A derived figure is traceable to the arithmetic that produced it, ask or no ask."""

    result, log = await summarise(monkeypatch, salary_only())

    assert result["calculator"] == "cashflow.v1"
    assert log.calculator_versions == ["cashflow.v1"]
    assert log.evidence_ids == ["inc_1"]


async def test_every_emi_example_states_a_tenure():

    """An example the capture skill would refuse teaches the wrong sentence, and EMIs need a term."""

    from app.ui.asks import ASKS

    emis = [ask for ask in ASKS if ask.kind == "emis"][0]

    assert emis.examples

    assert all("year" in example for example in emis.examples)


async def test_the_workspace_panel_is_not_sent_the_ask():

    """The panel keeps its own checklist, so the figures it renders must not repeat the questions."""

    from app.calculations.cashflow.v1 import CashflowInput, run_cashflow
    from app.ui.cashflow import cashflow_blocks

    records = salary_only()

    computed = run_cashflow(CashflowInput(income=[record.monthly_amount for record in records.income]))

    assert not only(cashflow_blocks(computed, records), "prompt")
