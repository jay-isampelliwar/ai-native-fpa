"""Rendering a computed cash flow, in the one place both the panel and the agent read it from.

These two functions used to live on ``CashflowSummarySkill``, which meant the workspace panel imported
a skill in order to draw a chart. That was always the wrong dependency and it became an impossible one
when the skills were replaced by tools: the panel does not answer questions, it renders figures, and
what it needed from that skill was never the skill.

So the rendering lives here, beside the blocks it produces, and both callers hand it a
``CashflowResult`` they already have. Neither recomputes anything - the calculator ran once, upstream,
and these turn its output into something to look at or something to read.

``describe_cashflow`` assembles its sentence entirely from computed figures. That property is the
reason it is a function rather than a prompt: the agent may quote this sentence, and every number in
it came from ``cashflow.v1`` rather than from a model that had seen the rows.

Warnings are surfaced rather than smoothed over, in both renderings. A month running at a deficit is
the finding, and a summary reporting the surplus without mentioning it would be technically accurate
and practically useless.

Evidence is attached per block rather than once for the set. The income figure cites the income rows
and the committed outflow cites the expenses and EMIs, so tapping a number shows the rows that made
that number rather than every row the answer touched.
"""

from decimal import Decimal

from app.calculations.cashflow.v1 import CashflowResult
from app.models.finance import CashflowRecords
from app.ui.blocks import Block
from app.ui.builders import amount_chart, amount_table, kpi, note


def format_rupees(amount: Decimal) -> str:

    """Render an amount the way an Indian statement would, so the user can match it against their own."""

    return f"INR {amount:,.0f}"


def cashflow_blocks(result: CashflowResult, records: CashflowRecords) -> list[Block]:

    """Render the computed figures as blocks, citing the records behind each one."""

    income_ids = [record.id for record in records.income]
    outflow_ids = [record.id for record in records.expenses] + [record.id for record in records.emis]

    blocks: list[Block] = [
        kpi(
            "Free surplus",
            result.free_surplus,
            records.evidence_ids,
            caption=f"{result.savings_rate_percent}% savings rate",
        ),
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


def describe_cashflow(result: CashflowResult) -> str:

    """Assemble the summary sentence from computed figures only, so nothing in the text was invented."""

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


def record_counts(records: CashflowRecords) -> dict[str, int]:

    """Count what this person has of each record type, in the keys the shared ask is written against."""

    return {
        "income": len(records.income),
        "expenses": len(records.expenses),
        "emis": len(records.emis),
        "sips": len(records.sips),
    }
