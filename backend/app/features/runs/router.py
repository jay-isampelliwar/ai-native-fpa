"""The runs routes: start a run for one user message, stream its events, cancel it, and decide its approvals."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_session
from app.features.approvals.exceptions import ApprovalExpired, ApprovalNotFound, ApprovalNotPending
from app.features.approvals.schemas import ApprovalDecisionRequest
from app.features.approvals.service import ApprovalService
from app.features.runs.exceptions import ConversationNotFound, RunAlreadyActive, RunNotFound
from app.features.runs.repository import RunRepository
from app.features.runs.schemas import CreateRunRequest, RunResponse
from app.features.runs.service import RunService
from app.features.runs.stream import follow


router = APIRouter(prefix="/runs", tags=["runs"])

SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}


def last_seen(last_event_id: str | None) -> int:

    """Read the number of the last event the listener saw from its Last-Event-ID header, or 0 when it has none."""

    if last_event_id is None or not last_event_id.isdigit():
        return 0

    return int(last_event_id)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    body: CreateRunRequest,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> RunResponse:

    """Start a run for the message, or return the run already started for this client request."""

    try:
        return await RunService(session).create_run(body, user_id)

    except ConversationNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found") from exc

    except RunAlreadyActive as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "A reply is still in progress in this conversation") from exc


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: int,
    after: int | None = Query(None, ge=0),
    last_event_id: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> StreamingResponse:

    """Stream the run's events after the last one the listener saw, given as Last-Event-ID or ?after=, until it ends or pauses."""

    if await RunRepository(session).get_run_for_user(run_id, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found") from RunNotFound(run_id)

    seen = after if after is not None else last_seen(last_event_id)

    return StreamingResponse(follow(run_id, seen), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> RunResponse:

    """Ask the run to stop; the final run.cancelled event arrives on the run's event stream."""

    try:
        return await RunService(session).cancel_run(run_id, user_id)

    except RunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found") from exc


@router.post("/{run_id}/approvals/{approval_id}")
async def decide_approval(
    run_id: int,
    approval_id: int,
    body: ApprovalDecisionRequest,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> RunResponse:

    """Approve or reject a paused tool call; the run carries on and its events stream again from /events."""

    try:
        return await ApprovalService(session).submit(run_id, approval_id, user_id, body.decision, body.edit_values())

    except ApprovalNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found") from exc

    except ApprovalNotPending as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This request was already answered") from exc

    except ApprovalExpired as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This request expired. Please ask again") from exc
