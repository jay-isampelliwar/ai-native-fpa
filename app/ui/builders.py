"""Helpers that turn calculator output into UI blocks, so no skill formats currency by hand.

Every skill needs the same handful of shapes - a headline figure, a breakdown, a caveat - and
every skill would otherwise write its own rupee formatting. One helper means one place where
grouping, decimals and the currency prefix are decided, and it means a KPI and the table under
it cannot disagree about how the same number looks.

``rupees`` drops the paisa on large figures deliberately. A surplus of "INR 61,000" is what a
person reads; "INR 61,000.00" reads like a machine and adds nothing, since the raw value travels
in the block's ``value`` field for anything that needs precision.

``tone`` is derived from the number rather than passed in. A negative surplus is negative
whichever skill produced it, and letting each caller decide would eventually produce a deficit
rendered in green.

Evidence is a required argument on every builder, not an optional one. A block without evidence
is a figure a user cannot trace, and making it easy to omit would guarantee it gets omitted.
"""

from decimal import Decimal

from app.ui.blocks import CalloutBlock, ChartBlock, ChartPoint, KpiBlock, TableBlock, TableColumn, TextBlock


def rupees(amount: Decimal, with_paisa: bool = False) -> str:

    """Format an amount the way an Indian statement does, dropping paisa unless it matters."""

    if with_paisa:
        return f"INR {amount:,.2f}"

    return f"INR {amount:,.0f}"


def tone_for(amount: Decimal) -> str:

    """Choose a KPI's tone from its sign, so a deficit is never rendered as good news."""

    if amount < Decimal("0"):
        return "negative"

    if amount > Decimal("0"):
        return "positive"

    return "neutral"


def kpi(label: str, amount: Decimal, evidence: list[str], caption: str | None = None) -> KpiBlock:

    """Build one headline figure with its formatted display, raw value and traceable evidence."""

    return KpiBlock(
        label=label,
        display=rupees(amount),
        value=amount,
        caption=caption,
        tone=tone_for(amount),
        evidence_ids=evidence,
    )


def text(body: str, evidence: list[str] | None = None) -> TextBlock:

    """Build a paragraph of explanation, which stays the fallback when nothing is worth showing."""

    return TextBlock(text=body, evidence_ids=evidence or [])


def note(body: str, level: str = "note", evidence: list[str] | None = None) -> CalloutBlock:

    """Build a caveat shown beside the figure it qualifies rather than buried in a field."""

    return CalloutBlock(level=level, text=body, evidence_ids=evidence or [])


def amount_table(
    title: str,
    rows: list[tuple[str, Decimal]],
    evidence: list[str],
    label_heading: str = "Item",
    ) -> TableBlock:

    """Build a two column table of labels and amounts, formatted once and aligned for reading."""

    return TableBlock(
        title=title,
        columns=[
            TableColumn(key="label", label=label_heading, align="left"),
            TableColumn(key="amount", label="Amount", align="right"),
        ],
        rows=[{"label": label, "amount": rupees(amount)} for label, amount in rows],
        evidence_ids=evidence,
    )


def amount_chart(
    title: str,
    points: list[tuple[str, Decimal]],
    evidence: list[str],
    chart: str = "bar",
    ) -> ChartBlock:

    """Build a chart from computed amounts, keeping the raw value beside each formatted label."""

    return ChartBlock(
        chart=chart,
        title=title,
        points=[ChartPoint(label=label, value=amount, display=rupees(amount)) for label, amount in points],
        evidence_ids=evidence,
    )
