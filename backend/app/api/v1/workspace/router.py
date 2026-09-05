"""The one endpoint the workspace panel reads, refreshed whenever a person's records change.

There is a single read and no writes. Everything that changes what this returns already has an
endpoint - a confirmed record, a committed import - so a second way to change the same state would
be a second thing to keep consistent.

It is not cached. The panel exists to show what the planner knows right now, and a stale surplus
rendered as current is precisely the failure the rest of this backend is shaped to avoid.
"""

from fastapi import APIRouter

from app.api.v1.workspace.schemas import WorkspaceRead, WorkspaceReadiness, WorkspaceSectionRead
from app.services.workspace import build_workspace

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceRead)
async def read_workspace(user_id: int) -> WorkspaceRead:

    """Return what is still needed from this person and every section there is data to show."""

    readiness, sections = await build_workspace(user_id)

    return WorkspaceRead(
        user_id=user_id,
        readiness=WorkspaceReadiness(**readiness),
        sections=[
            WorkspaceSectionRead(
                key=section.key,
                title=section.title,
                subtitle=section.subtitle,
                blocks=section.blocks,
            )
            for section in sections
        ],
    )
