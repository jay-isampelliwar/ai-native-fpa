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

Every section is computed independently and a failure in one is dropped rather than raised. A person
whose holdings import left something unreadable should still see their cash flow, and a panel that
renders nothing because one query failed is worse than a panel with a section missing.
"""

import structlog

from app.alerts.service import alert_service
from app.calculations.cashflow.v1 import CALCULATOR_VERSION, CashflowInput, run_cashflow
from app.graphs.skills.cashflow_summary.skill import CashflowSummarySkill
from app.repositories import get_cashflow_repository
from app.repositories.holdings_repository import holdings_repository
from app.ui.blocks import Block, CalloutBlock, KpiBlock, TableBlock, TableColumn

log = structlog.get_logger(__name__)

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

    portfolio = await safely(portfolio_section, user_id, "portfolio")

    if portfolio is not None:
        sections.append(portfolio)

    attention = await safely(alerts_section, user_id, "alerts")

    if attention is not None:
        sections.append(attention)

    return readiness, sections


async def safely(builder, user_id: int, key: str) -> WorkspaceSection | None:

    """Build one section, dropping it if it fails so one broken query cannot empty the whole panel."""

    try:
        return await builder(user_id)

    except Exception:

        log.warning("workspace.section_failed", section=key, user_id=user_id, exc_info=True)

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
        blocks=CashflowSummarySkill().build_blocks(result, records),
    )


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
            caption=f"{summary.count} holdings" + (f" as at {summary.valued_at}" if summary.valued_at else ""),
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
