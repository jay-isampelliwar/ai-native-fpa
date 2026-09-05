"""The shape of the workspace panel, which is a list of sections rather than a fixed dashboard.

Sections are returned as a list and the client renders them in order. A fixed response with one field
per widget would mean adding a widget is a change to the client, the schema and the service; a list
means the backend decides what a person can currently be shown and the client renders whatever
arrives. That matters here because which sections exist is data dependent, not layout dependent.

``blocks`` is the same union the chat returns. The panel is not a second rendering vocabulary - a
figure shown there is built by the same code, cites the same evidence and formats through the same
``display`` string, so the surplus in the panel and the surplus in the answer cannot disagree.

``readiness`` is separate from the sections because it is present even when nothing else is. It is
what the panel shows a person who has given nothing yet, and it stays afterwards as the record of
what is still missing.
"""

from pydantic import BaseModel, Field

from app.ui.blocks import Block


class WorkspaceReadiness(BaseModel):

    """Which cash flow inputs this person has given, and which are still missing."""

    held: dict[str, int] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    can_compute_cashflow: bool = False
    has_any_records: bool = False


class WorkspaceSectionRead(BaseModel):

    """One panel of the workspace, carrying the same typed blocks the conversation renders."""

    key: str
    title: str
    subtitle: str | None = None
    blocks: list[Block] = Field(default_factory=list)


class WorkspaceRead(BaseModel):

    """Everything the panel shows: what is still needed, and every section there is data for."""

    user_id: int
    readiness: WorkspaceReadiness
    sections: list[WorkspaceSectionRead] = Field(default_factory=list)
