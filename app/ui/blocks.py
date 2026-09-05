"""The typed UI blocks a skill returns, and the only vocabulary the frontend renders.

The model never emits markup. A skill returns a list of these blocks, the frontend maps each
``type`` to a component from a fixed registry, and anything outside that vocabulary simply has
no renderer. That is what keeps a generated interface from becoming an unauditable one: a chart
can only appear because a skill built a ``ChartBlock`` from computed figures, never because a
model wrote some JSX.

Every block carries its own ``evidence_ids``. Attaching evidence at the result level would say
"these six rows produced this answer" while leaving no way to know which row is behind the KPI a
user is squinting at. Per block, a user can tap a figure and see exactly what it came from, and
the validator can check that no block cites a row the skill never read.

Numeric values are ``Decimal`` and are serialised as strings. A chart that round trips through a
float has already lost the precision ``app.calculations.money`` exists to protect, and a table
showing a total that differs from the KPI above it by a paisa is a bug users notice immediately.

``display`` and ``value`` are separate on purpose. ``display`` is the formatted string the
backend chose - rupee grouping, no decimals for large sums - and ``value`` is the raw figure a
chart needs to scale an axis. Letting the frontend format from raw would put currency rendering
in two places and guarantee they drift.

``ApprovalCardBlock`` is the one block tied to a graph state rather than to a calculation. It
renders what ``request_approval`` interrupted with, and its ``approval_id`` is what the client
posts back - so a user approves the exact proposal they were shown rather than a fresh one.
"""

from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class BlockBase(BaseModel):

    """Fields every block shares, chiefly the evidence that makes one figure traceable."""

    model_config = {"arbitrary_types_allowed": True}

    evidence_ids: list[str] = Field(default_factory=list)


class TextBlock(BlockBase):

    """A paragraph of explanation, which is what a skill returns when there is nothing to show."""

    type: Literal["text"] = "text"
    text: str


class KpiBlock(BlockBase):

    """One headline figure, the block a user reads first and therefore the one most worth tracing."""

    type: Literal["kpi"] = "kpi"
    label: str
    display: str
    value: Decimal | None = None
    caption: str | None = None
    tone: Literal["neutral", "positive", "negative"] = "neutral"


class TableColumn(BaseModel):

    """One column of a table, carrying the alignment the data type implies."""

    key: str
    label: str
    align: Literal["left", "right"] = "left"


class TableBlock(BlockBase):

    """Rows of already formatted values, used where a chart would obscure the detail."""

    type: Literal["table"] = "table"
    title: str | None = None
    columns: list[TableColumn]
    rows: list[dict[str, str]] = Field(default_factory=list)


class ChartPoint(BaseModel):

    """One plotted value, keeping the raw figure beside the label the axis shows."""

    model_config = {"arbitrary_types_allowed": True}

    label: str
    value: Decimal
    display: str | None = None


class ChartBlock(BlockBase):

    """A small chart built from computed figures, never from anything a model produced."""

    type: Literal["chart"] = "chart"
    chart: Literal["bar", "line", "donut"] = "bar"
    title: str | None = None
    points: list[ChartPoint] = Field(default_factory=list)
    value_prefix: str = "INR "


class CalloutBlock(BlockBase):

    """A warning or caveat surfaced where the user reads the number, not buried in a field."""

    type: Literal["callout"] = "callout"
    level: Literal["note", "warning"] = "note"
    text: str


class FieldChange(BaseModel):

    """One field of a proposed change, showing the before and after a user is approving."""

    label: str
    before: str | None = None
    after: str


class ApprovalCardBlock(BlockBase):

    """The proposed change a paused run is waiting on, rendered so the user can see exactly what alters."""

    type: Literal["approval_card"] = "approval_card"
    title: str
    changes: list[FieldChange] = Field(default_factory=list)
    approval_id: str | None = None
    expires_in_seconds: int = 0


Block = Annotated[
    Union[
        TextBlock,
        KpiBlock,
        TableBlock,
        ChartBlock,
        CalloutBlock,
        ApprovalCardBlock,
    ],
    Field(discriminator="type"),
]

BLOCK_TYPES = frozenset({"text", "kpi", "table", "chart", "callout", "approval_card"})
