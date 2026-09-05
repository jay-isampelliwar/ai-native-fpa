"""The cash flow summary skill: read the records, run the calculator, describe the result.

This is the simplest shape a skill can take and the one most of the low risk catalogue
will follow. There is no agent loop and no tool selection, because the question has a
single deterministic answer: fetch this user's records, hand the monthly amounts to the
versioned calculator, and report what came back.

No model is called. Every number in the returned message comes from ``cashflow.v1`` and
every sentence is assembled by ``_summarise``, so the figures a user reads cannot drift
from the figures that were computed. The explanation model is added later, and when it is
it will be given the finished numbers to narrate rather than the records to reason over.

The skill returns evidence ids and the calculator version on every answer. That is what
makes the reply auditable: a user who disputes the surplus can be shown the exact rows
and the exact formula version behind it.

Warnings from the calculator are surfaced rather than smoothed over. A month running at a
deficit is the finding, and a summary that reported the surplus without mentioning it
would be technically accurate and practically useless.

The repository is injected rather than imported at use time, so tests supply a fixture
user and the same skill code runs unchanged against SQL later.

Blocks and message are built from the same ``CashflowResult`` in the same call. They are two
renderings of one set of figures, and deriving them separately - or letting the message come
from somewhere the blocks did not - is how a headline number ends up disagreeing with the table
beneath it.
"""

from decimal import Decimal

from app.calculations.cashflow.v1 import CALCULATOR_VERSION, CashflowInput, CashflowResult, run_cashflow
from app.graphs.skills.cashflow_summary.definition import DEFINITION
from app.graphs.skills.contracts import SkillContext, SkillRequest, SkillResult
from app.models.finance import CashflowRecords
from app.repositories import get_cashflow_repository
from app.repositories.cashflow_repository import CashflowRepository
from app.ui.blocks import Block
from app.ui.builders import amount_chart, amount_table, kpi, note


def format_rupees(amount: Decimal) -> str:

    """Render an amount the way an Indian statement would, so the user can match it against their own."""

    return f"INR {amount:,.0f}"


class CashflowSummarySkill:

    """Answers this month's surplus question from verified records and one versioned calculator."""

    name = DEFINITION.name
    version = DEFINITION.version

    def __init__(self, repository: CashflowRepository | None = None) -> None:

        """Take the repository to read from, defaulting to the configured one and injectable in tests."""

        self._repository = repository or get_cashflow_repository()

    async def execute(
        self,
        request: SkillRequest,
        context: SkillContext,
        ) -> SkillResult:

        """Fetch the caller's records, compute their monthly cash flow and report it with its evidence."""

        records = await self._repository.get_cashflow_records(context.user_id)

        if not records.evidence_ids:
            return SkillResult(
                status="refused",
                message="I have no income or expense records for you yet, so I cannot summarise your cash flow.",
            )

        inputs = CashflowInput(
            income=[record.monthly_amount for record in records.income],
            expenses=[record.monthly_amount for record in records.expenses],
            emis=[record.monthly_amount for record in records.emis],
            sips=[record.monthly_amount for record in records.sips],
        )

        result = run_cashflow(inputs)

        return SkillResult(
            status="answered",
            message=self.summarise(result),
            blocks=self.build_blocks(result, records),
            evidence_ids=records.evidence_ids,
            calculator_versions=[CALCULATOR_VERSION],
            assumptions={"months_per_year": 12.0},
        )

    def build_blocks(self, result: CashflowResult, records: CashflowRecords) -> list[Block]:

        """Render the same computed figures as blocks, citing the records behind each one."""

        income_ids = [record.id for record in records.income]
        outflow_ids = [record.id for record in records.expenses] + [record.id for record in records.emis]
        sip_ids = [record.id for record in records.sips]

        blocks: list[Block] = [
            kpi("Free surplus", result.free_surplus, records.evidence_ids,
                caption=f"{result.savings_rate_percent}% savings rate"),
            kpi("Income", result.total_income, income_ids),
            kpi("Committed outflow", result.committed_outflow, outflow_ids),
        ]

        breakdown = [
            ("Expenses", result.total_expenses),
            ("EMIs", result.total_emis),
            ("SIPs", result.total_sips),
            ("Left over", result.free_surplus),
        ]

        blocks.append(amount_chart("Where this month goes", breakdown, records.evidence_ids, chart="donut"))

        blocks.append(
            amount_table(
                "This month",
                [("Income", result.total_income)] + breakdown,
                records.evidence_ids,
            )
        )

        for warning in result.warnings:
            blocks.append(note(warning, level="warning", evidence=records.evidence_ids))

        return blocks

    def summarise(self, result: CashflowResult) -> str:

        """Assemble the reply from computed figures only, so nothing in the text was invented."""

        lines = [
            f"Income this month is {format_rupees(result.total_income)}.",
            f"Committed outflow is {format_rupees(result.committed_outflow)}, "
            f"of which EMIs are {format_rupees(result.total_emis)}.",
            f"SIPs take {format_rupees(result.total_sips)}.",
            f"That leaves a free surplus of {format_rupees(result.free_surplus)}, "
            f"a savings rate of {result.savings_rate_percent}%.",
        ]

        for warning in result.warnings:
            lines.append(f"Note: {warning}.")

        return " ".join(lines)
