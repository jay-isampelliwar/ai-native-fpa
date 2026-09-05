"""The four steps of a goal projection, each a plain function with no model involved.

The order is fixed because the question has one shape. ``resolve_goal`` decides which goal is
being asked about, ``load_cashflow`` finds what the user can actually spare, ``project_goal``
runs the versioned calculator, and ``compose_answer`` turns the figures into a paragraph.
Nothing branches on anything a model produced.

``resolve_goal`` matches on words from the question before falling back to priority order. That
is deliberately simple and deliberately not a model call: picking the wrong goal produces a
confidently wrong answer about a different large sum, and a rule a user can be told - "I matched
'house'" - is auditable in a way an inference is not. The chosen goal is always named in the
answer so a mismatch is visible rather than silent.

``load_cashflow`` uses ``investable_surplus`` rather than ``free_surplus`` when judging whether
a required contribution is affordable. The question is how much could go towards this goal, and
money already committed to an SIP is redirectable in a way rent is not.

``compose_answer`` writes every sentence from computed values. No figure in the text is
produced by a model, so the paragraph and the projection cannot disagree.

Warnings from both calculators are carried into the answer rather than dropped. A projection
that assumes returns beating inflation should say so where the user reads it, not only in a
field they may never see.

Evidence is merged rather than concatenated. Two nodes legitimately read the same row - an SIP
funds the goal and also appears in the cash flow - and a repeated id in the evidence set makes
one record look like two pieces of corroboration when it is one.
"""

from decimal import Decimal

from app.calculations.cashflow.v1 import CALCULATOR_VERSION as CASHFLOW_VERSION
from app.calculations.cashflow.v1 import CashflowInput, run_cashflow
from app.calculations.goals.v1 import CALCULATOR_VERSION as GOALS_VERSION
from app.calculations.goals.v1 import GoalInput, run_goal_projection
from app.core.config import settings
from app.graphs.skills.goal_planning.schemas import GoalPlanningState
from app.repositories import get_cashflow_repository
from app.repositories.goals_repository import goals_repository
from app.ui.blocks import Block
from app.ui.builders import amount_chart, amount_table, kpi, note
from app.utils.dates import today_in_timezone

STOP_WORDS = frozenset({"my", "the", "a", "for", "to", "can", "i", "afford", "goal", "buy", "will", "reach"})


def merge_evidence(*groups: list[str]) -> list[str]:

    """Combine evidence lists into one, keeping first appearance order and dropping repeats."""

    merged: dict[str, None] = {}

    for group in groups:
        for identifier in group:
            merged.setdefault(identifier, None)

    return list(merged)


def format_rupees(amount: Decimal) -> str:

    """Render an amount the way an Indian statement would, so a user can match it against theirs."""

    return f"INR {amount:,.0f}"


async def resolve_goal(state: GoalPlanningState) -> dict:

    """Choose which goal the question is about, preferring a word match and falling back to priority."""

    snapshots = await goals_repository.list_snapshots(state.user_id)

    if not snapshots:
        return {"failure_reason": "no goals have been set up yet"}

    words = {word.strip(".,?!").lower() for word in state.message.split()} - STOP_WORDS

    for snapshot in snapshots:

        label_words = {word.lower() for word in snapshot.label.split()}

        if words & label_words:
            return {"snapshot": snapshot, "evidence_ids": snapshot.evidence_ids}

    chosen = snapshots[0]

    return {"snapshot": chosen, "evidence_ids": chosen.evidence_ids}


async def load_cashflow(state: GoalPlanningState) -> dict:

    """Read the caller's cash flow so the required contribution can be judged against real surplus."""

    if state.snapshot is None:
        return {}

    records = await get_cashflow_repository().get_cashflow_records(state.user_id)

    result = run_cashflow(
        CashflowInput(
            income=[record.monthly_amount for record in records.income],
            expenses=[record.monthly_amount for record in records.expenses],
            emis=[record.monthly_amount for record in records.emis],
            sips=[record.monthly_amount for record in records.sips],
        )
    )

    return {
        "cashflow": result,
        "surplus_available": result.investable_surplus,
        "evidence_ids": merge_evidence(state.evidence_ids, records.evidence_ids),
        "calculator_versions": [CASHFLOW_VERSION],
    }


def project_goal(state: GoalPlanningState) -> dict:

    """Run the versioned goal calculator against the resolved goal and its current funding."""

    snapshot = state.snapshot

    if snapshot is None:
        return {}

    projection = run_goal_projection(
        GoalInput(
            target_amount=snapshot.target_amount,
            target_date=snapshot.target_date,
            as_of=today_in_timezone(settings.default_timezone),
            current_corpus=snapshot.funded_corpus,
            monthly_contribution=snapshot.monthly_contribution,
            inflation_percent=snapshot.inflation_percent,
        )
    )

    affordable = None

    if state.surplus_available is not None:
        affordable = projection.required_monthly <= state.surplus_available

    return {
        "projection": projection,
        "affordable": affordable,
        "calculator_versions": state.calculator_versions + [GOALS_VERSION],
        "assumptions": projection.assumptions,
    }


def compose_answer(state: GoalPlanningState) -> dict:

    """Write the reply entirely from computed figures, so the text cannot drift from the projection."""

    if state.failure_reason:
        return {"answer": f"I could not project that: {state.failure_reason}."}

    snapshot = state.snapshot
    projection = state.projection

    if snapshot is None or projection is None:
        return {"answer": "I could not project that goal."}

    lines = [
        f"{snapshot.label}: {format_rupees(snapshot.target_amount)} by "
        f"{snapshot.target_date.strftime('%B %Y')}, which is {projection.months_remaining} months away.",
        f"Allowing for inflation that target becomes {format_rupees(projection.target_at_maturity)}.",
        f"What is funding it today grows to {format_rupees(projection.projected_corpus)}.",
    ]

    if projection.on_track:
        lines.append("That already covers the target, so no additional contribution is needed.")

    else:
        lines.append(
            f"That leaves a shortfall of {format_rupees(projection.shortfall)}, "
            f"which needs {format_rupees(projection.required_monthly)} a month from now."
        )

        if state.surplus_available is not None:
            lines.append(
                f"Your investable surplus is {format_rupees(state.surplus_available)} a month, "
                + ("so that is affordable." if state.affordable else "so that is more than you currently have spare.")
            )

    if snapshot.valued_at_cost and snapshot.funded_corpus > Decimal("0"):
        lines.append("Holdings are valued at cost, not at market price.")

    for warning in projection.warnings:
        lines.append(f"Note: {warning}.")

    if state.cashflow is not None:
        for warning in state.cashflow.warnings:
            lines.append(f"Note: {warning}.")

    return {"answer": " ".join(lines), "blocks": build_blocks(state)}


def build_blocks(state: GoalPlanningState) -> list[Block]:

    """Render the projection as blocks, citing the goal and the records behind each figure."""

    snapshot = state.snapshot
    projection = state.projection

    if snapshot is None or projection is None:
        return []

    evidence = state.evidence_ids

    blocks: list[Block] = [
        kpi(
            "Shortfall" if not projection.on_track else "Surplus to target",
            projection.shortfall,
            evidence,
            caption=f"{projection.months_remaining} months to {snapshot.target_date.strftime('%b %Y')}",
        ),
        kpi("Needed each month", projection.required_monthly, evidence),
    ]

    if state.surplus_available is not None:
        blocks.append(kpi("Investable surplus", state.surplus_available, evidence))

    blocks.append(
        amount_chart(
            f"{snapshot.label}: projected against target",
            [
                ("Funding today", snapshot.funded_corpus),
                ("Grows to", projection.projected_corpus),
                ("Target then", projection.target_at_maturity),
            ],
            evidence,
        )
    )

    blocks.append(
        amount_table(
            snapshot.label,
            [
                ("Target today", projection.target_today),
                ("Target at maturity", projection.target_at_maturity),
                ("Funded now", snapshot.funded_corpus),
                ("Monthly contribution", snapshot.monthly_contribution),
                ("Projected corpus", projection.projected_corpus),
                ("Shortfall", projection.shortfall),
            ],
            evidence,
        )
    )

    if snapshot.valued_at_cost and snapshot.funded_corpus > Decimal("0"):
        blocks.append(note("Holdings are valued at cost, not at market price.", evidence=evidence))

    for warning in projection.warnings:
        blocks.append(note(warning, level="warning", evidence=evidence))

    return blocks
