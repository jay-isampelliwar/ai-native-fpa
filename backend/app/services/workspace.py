"""What the workspace panel shows, assembled from whatever records a person has actually given.

The conversation answers questions; this answers "what do you know about me right now". It is built
because a chat is the wrong shape for a standing view of someone's money: an answer scrolls away, and
the surplus a person wants to keep glancing at ends up four questions up the thread. The panel holds
the same typed blocks a skill returns, so nothing here invents a way of showing a figure that a skill
could not also have produced.

Sections appear when their data does, and that is the whole behaviour. Cash flow appears the moment
there is anything to compute it from, the portfolio when a statement has been committed, alerts when
something is worth saying. Rendering an empty widget with dashes in it would teach a person to ignore
the panel; leaving it out means its appearance is information.

Readiness is always present and is the panel's job before it has data. It reports which of the four
cash flow inputs are missing, so a new person sees a checklist rather than a blank page, and can
watch it fill in as they answer.

Nothing here calls a model and nothing here writes. A panel that re-derived figures differently from
the skill that answered the same question in the chat would be two sources of truth about one number,
which is why the cash flow section runs the same versioned calculator the skill does rather than its
own arithmetic.

Goals and retirement are projected here rather than read. A goal row holds what something costs in
today's money and the year it is wanted; what it will cost by then, what the current funding grows
to, and whether that is enough are all computed at read time by ``goals.v1`` - the same calculator
the chat skill runs, so the panel and an answer cannot disagree about whether a goal is on track.

An unfunded goal is drawn as what would reach it rather than as a flat zero. Funding is what a person
has explicitly linked to a goal, and a plan imported this morning has linked nothing - so the honest
projection is a line along the bottom, which tells them only that they have done nothing. The curve
instead shows the corpus the required contribution would build, says plainly that this is what the
figure means, and asks them to link something. The number is still the calculator's: it is the
``required_monthly`` from the same projection, not an amount this file chose.

Retirement is a goal, not a separate thing. It is the goal whose kind says so, drawn as a curve
towards the corpus it needs instead of as a progress bar, because the shape of thirty years of
compounding is the part worth seeing. The curve is the same projection run at each year rather than a
second formula, so no figure on it comes from arithmetic this file invented.

The portfolio says how old it is, because nothing in this system fetches a price. Values come from
whatever statement was last imported and never move afterwards, so a total presented without a date
is a claim about today made from figures that may be months old. The panel dates it by the oldest
holding rather than the newest - a portfolio is only as current as its stalest line - and says so
outright once it passes ``stale_valuation_days``.

Every section is computed independently and a failure in one is dropped rather than raised. A person
whose holdings import left something unreadable should still see their cash flow, and a panel that
renders nothing because one query failed is worse than a panel with a section missing.
"""

from datetime import date
from decimal import Decimal

from app.alerts.service import alert_service
from app.core.config import settings
from app.calculations.cashflow.v1 import CALCULATOR_VERSION, CashflowInput, run_cashflow
from app.calculations.goals.v1 import CALCULATOR_VERSION as GOALS_CALCULATOR, GoalInput, run_goal_projection
from app.repositories import get_cashflow_repository
from app.repositories.goals_repository import goals_repository
from app.repositories.holdings_repository import holdings_repository
from app.services.projections import projected_goals
from app.ui.blocks import Block, CalloutBlock, ChartBlock, ChartMarker, ChartPoint, KpiBlock, TableBlock, TableColumn
from app.ui.cashflow import cashflow_blocks
from app.ui.builders import kpi, note, rupees

READINESS_LABELS = {
    "income": "Income",
    "expenses": "Regular expenses",
    "emis": "Loan EMIs",
    "sips": "SIPs",
}

REQUIRED_FOR_CASHFLOW = ("income", "expenses")


class WorkspaceSection:

    """One panel of the workspace: a heading, the blocks under it, and why it is there."""

    def __init__(self, key: str, title: str, blocks: list[Block], subtitle: str | None = None) -> None:

        """Hold one section's identity and content, kept as a plain object the router narrows."""

        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.blocks = blocks


async def build_workspace(user_id: int) -> tuple[dict, list[WorkspaceSection]]:

    """Assemble the readiness summary and every section this person currently has the data for."""

    sections: list[WorkspaceSection] = []

    readiness = await build_readiness(user_id)

    cashflow = await safely(cashflow_section, user_id, "cashflow")

    if cashflow is not None:
        sections.append(cashflow)

    goals = await safely(goals_section, user_id, "goals")

    if goals is not None:
        sections.append(goals)

    retirement = await safely(retirement_section, user_id, "retirement")

    if retirement is not None:
        sections.append(retirement)

    portfolio = await safely(portfolio_section, user_id, "portfolio")

    if portfolio is not None:
        sections.append(portfolio)

    attention = await safely(alerts_section, user_id, "alerts")

    if attention is not None:
        sections.append(attention)

    return readiness, sections


async def goals_section(user_id: int) -> WorkspaceSection | None:

    """Show every goal against what is actually funding it, projected by the same calculator the chat uses."""

    goals = await projected_goals(user_id)

    if not goals:
        return None

    blocks: list[Block] = []

    rows: list[dict[str, str]] = []

    for snapshot, projection in ((goal.snapshot, goal.projection) for goal in goals):

        reached = share_of(projection.projected_corpus, projection.target_at_maturity)

        blocks.append(
            ChartBlock(
                chart="progress",
                title=snapshot.label,
                caption=(
                    f"{snapshot.target_date.year} · on track"
                    if projection.on_track
                    else f"{snapshot.target_date.year} · short by {rupees(projection.shortfall)}"
                ),
                points=[
                    ChartPoint(
                        label="on the way",
                        value=reached,
                        display=f"{reached}%",
                        tone="positive" if projection.on_track else "negative",
                    )
                ],
                marker=ChartMarker(
                    label="needed",
                    value=projection.target_at_maturity,
                    display=rupees(projection.target_at_maturity),
                ),
                evidence_ids=snapshot.evidence_ids,
            )
        )

        rows.append(
            {
                "goal": snapshot.label,
                "by": str(snapshot.target_date.year),
                "needed": rupees(projection.target_at_maturity),
                "monthly": rupees(projection.required_monthly),
            }
        )

    blocks.append(
        TableBlock(
            title="What each goal asks of you",
            columns=[
                TableColumn(key="goal", label="Goal", align="left"),
                TableColumn(key="by", label="By", align="right"),
                TableColumn(key="needed", label="Needed then", align="right"),
                TableColumn(key="monthly", label="Per month", align="right"),
            ],
            rows=rows,
        )
    )

    return WorkspaceSection(
        key="goals",
        title="Goals",
        subtitle=f"projected by {GOALS_CALCULATOR}",
        blocks=blocks,
    )


async def retirement_section(user_id: int) -> WorkspaceSection | None:

    """Draw the retirement goal as a corpus growing towards the figure it has to reach."""

    snapshots = [goal for goal in await goals_repository.list_snapshots(user_id) if goal.kind == "retirement"]

    if not snapshots:
        return None

    snapshot = snapshots[0]

    today = date.today()

    projection = run_goal_projection(
        GoalInput(
            target_amount=snapshot.target_amount,
            target_date=snapshot.target_date,
            as_of=today,
            current_corpus=snapshot.funded_corpus,
            monthly_contribution=snapshot.monthly_contribution,
            inflation_percent=snapshot.inflation_percent,
        )
    )

    funding = snapshot.monthly_contribution or projection.required_monthly

    blocks: list[Block] = [
        kpi(
            "Corpus by " + str(snapshot.target_date.year),
            projection.projected_corpus,
            snapshot.evidence_ids,
            caption=f"needs {rupees(projection.target_at_maturity)} in that year's money",
        ),
        ChartBlock(
            chart="line",
            title="How the corpus grows",
            caption=(
                "on what is funding it today"
                if snapshot.monthly_contribution
                else f"if {rupees(funding)} a month went towards it, which is what reaches it"
            ),
            points=corpus_curve(snapshot, today, funding),
            marker=ChartMarker(
                label="needed",
                value=projection.target_at_maturity,
                display=rupees(projection.target_at_maturity),
            ),
            evidence_ids=snapshot.evidence_ids,
        ),
    ]

    if not snapshot.monthly_contribution and not snapshot.funded_corpus:
        blocks.append(
            note(
                f"Nothing is linked to this goal yet, so the curve shows what {rupees(funding)} a month "
                "would build rather than what your records are already doing. Link a SIP or a holding "
                "to it and this becomes a projection of your own money.",
                level="note",
            )
        )

    return WorkspaceSection(
        key="retirement",
        title="Retirement",
        subtitle=f"projected by {GOALS_CALCULATOR}",
        blocks=blocks,
    )


def corpus_curve(snapshot, today: date, monthly: Decimal) -> list[ChartPoint]:

    """Plot the same projection year by year, so the shape of the growth is visible rather than only its end."""

    years = max(snapshot.target_date.year - today.year, 1)

    step = max(years // 8, 1)

    points: list[ChartPoint] = []

    for offset in list(range(0, years, step)) + [years]:

        at = date(today.year + offset, today.month, 1)

        projection = run_goal_projection(
            GoalInput(
                target_amount=snapshot.target_amount,
                target_date=at,
                as_of=today,
                current_corpus=snapshot.funded_corpus,
                monthly_contribution=monthly,
                inflation_percent=snapshot.inflation_percent,
            )
        )

        points.append(
            ChartPoint(
                label=str(at.year),
                value=projection.projected_corpus,
                display=rupees(projection.projected_corpus),
            )
        )

    return points


def share_of(part: Decimal, whole: Decimal) -> Decimal:

    """Express one figure as a percentage of another, capped at a hundred and safe when the whole is zero."""

    if whole <= Decimal("0"):
        return Decimal("100")

    return min((part / whole * Decimal("100")).quantize(Decimal("1")), Decimal("100"))


async def safely(builder, user_id: int, key: str) -> WorkspaceSection | None:

    """Build one section, dropping it if it fails so one broken query cannot empty the whole panel."""

    try:
        return await builder(user_id)

    except Exception:
        return None


async def build_readiness(user_id: int) -> dict:

    """Report which cash flow inputs this person has given and which are still missing."""

    records = await get_cashflow_repository().get_cashflow_records(user_id)

    held = {
        "income": len(records.income),
        "expenses": len(records.expenses),
        "emis": len(records.emis),
        "sips": len(records.sips),
    }

    missing = [name for name, count in held.items() if count == 0]

    return {
        "held": held,
        "missing": missing,
        "labels": READINESS_LABELS,
        "can_compute_cashflow": all(held[name] for name in REQUIRED_FOR_CASHFLOW),
        "has_any_records": any(held.values()),
    }


async def cashflow_section(user_id: int) -> WorkspaceSection | None:

    """Run the same versioned calculator the chat skill runs, so one number cannot have two answers."""

    records = await get_cashflow_repository().get_cashflow_records(user_id)

    if not records.evidence_ids:
        return None

    result = run_cashflow(
        CashflowInput(
            income=[record.monthly_amount for record in records.income],
            expenses=[record.monthly_amount for record in records.expenses],
            emis=[record.monthly_amount for record in records.emis],
            sips=[record.monthly_amount for record in records.sips],
        )
    )

    return WorkspaceSection(
        key="cashflow",
        title="This month",
        subtitle=f"computed by {CALCULATOR_VERSION}",
        blocks=cashflow_blocks(result, records),
    )


def valuation_caption(summary) -> str:

    """Say what the portfolio total is worth and, more importantly, when it was last true."""

    holdings = f"{summary.count} holding{'' if summary.count == 1 else 's'}"

    if not summary.oldest_valued_at:
        return holdings

    if summary.stale_days > settings.stale_valuation_days:
        return f"{holdings} · valued {summary.stale_days} days ago, on {summary.oldest_valued_at}"

    return f"{holdings} · as your statements stated on {summary.valued_at}"


async def portfolio_section(user_id: int) -> WorkspaceSection | None:

    """Show what has been imported, which only exists once a statement has been committed."""

    summary = await holdings_repository.summary(user_id)

    if summary.count == 0:
        return None

    blocks: list[Block] = [
        KpiBlock(
            label="Portfolio value",
            display=f"₹{summary.current_value:,.0f}",
            value=summary.current_value,
            caption=valuation_caption(summary),
            tone="neutral",
        ),
        KpiBlock(
            label="Unrealised",
            display=f"₹{summary.unrealised:,.0f}",
            value=summary.unrealised,
            caption=f"invested ₹{summary.invested_value:,.0f}",
            tone="positive" if summary.unrealised >= 0 else "negative",
        ),
    ]

    if summary.by_asset_type:
        blocks.append(
            TableBlock(
                title="By asset type",
                columns=[
                    TableColumn(key="type", label="Type", align="left"),
                    TableColumn(key="value", label="Value", align="right"),
                ],
                rows=[
                    {"type": name.replace("_", " ").title(), "value": f"₹{value:,.0f}"}
                    for name, value in summary.by_asset_type.items()
                ],
            )
        )

    if summary.stale_days > settings.stale_valuation_days:
        blocks.append(
            CalloutBlock(
                level="warning",
                text=(
                    f"These values are what your statements said on {summary.oldest_valued_at}, "
                    f"{summary.stale_days} days ago. Nothing here is a live price - upload a newer "
                    "statement to bring them up to date."
                ),
            )
        )

    return WorkspaceSection(key="portfolio", title="Portfolio", blocks=blocks)


async def alerts_section(user_id: int) -> WorkspaceSection | None:

    """Surface what the system wants to say first, which is the one place it speaks unprompted."""

    findings = await alert_service.evaluate(user_id)

    if not findings:
        return None

    return WorkspaceSection(
        key="alerts",
        title="Needs attention",
        blocks=[
            CalloutBlock(
                level="warning" if alert.severity == "action" else "note",
                text=f"{alert.title}. {alert.detail}",
                evidence_ids=alert.evidence_ids,
            )
            for alert in findings
        ],
    )
