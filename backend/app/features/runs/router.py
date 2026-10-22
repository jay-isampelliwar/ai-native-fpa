"""The runs routes: start a run for one user message, stream its events, cancel it, and decide its approvals."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.enums import RunStatus
from app.db.session import get_session
from app.features.approvals.exceptions import ApprovalExpired, ApprovalNotFound, ApprovalNotPending
from app.features.approvals.repository import ApprovalRepository
from app.features.approvals.schemas import ApprovalDecisionRequest
from app.features.approvals.service import ApprovalService
from app.features.runs.events import FINAL_EVENT_FOR_STATUS, RunEvent, run_events
from app.features.runs.exceptions import ConversationNotFound, RunAlreadyActive, RunNotFound
from app.features.runs.repository import RunRepository
from app.features.runs.schemas import CreateRunRequest, RunResponse
from app.features.runs.service import RunService
from app.features.runs.worker import approval_event


router = APIRouter(prefix="/runs", tags=["runs"])

SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}


async def as_sse(events: AsyncIterator[RunEvent]) -> AsyncIterator[str]:

    """Turn run events into server-sent event text."""

    async for event in events:
        yield event.to_sse()


async def one_event(event: RunEvent) -> AsyncIterator[RunEvent]:

    """Yield a single event, for a run that has already ended."""

    yield event


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
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    ) -> StreamingResponse:

    """Stream the run's events as server-sent events until it ends or pauses, sending a paused run's approval card at once."""

    queue = run_events.subscribe(run_id)

    repo = RunRepository(session)

    run = await repo.get_run_for_user(run_id, user_id)

    if run is None:

        run_events.stop_listening(run_id, queue)

        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found") from RunNotFound(run_id)

    final_event = FINAL_EVENT_FOR_STATUS.get(run.status)

    approval = None

    if run.status == RunStatus.awaiting_approval:
        approval = await ApprovalRepository(session).pending_for_run(run_id)

    if approval is not None:

        run_events.stop_listening(run_id, queue)

        events = one_event(approval_event(approval))

    elif final_event is not None:

        run_events.stop_listening(run_id, queue)

        message = await repo.get_assistant_message(run_id)

        text = message.content.get("text", "") if message is not None else ""

        events = one_event(RunEvent(final_event, {"status": run.status.value, "text": text}))

    else:
        events = run_events.drain(run_id, queue)

    return StreamingResponse(as_sse(events), media_type="text/event-stream", headers=SSE_HEADERS)


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
        return await ApprovalService(session).submit(run_id, approval_id, user_id, body.decision)

    except ApprovalNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found") from exc

    except ApprovalNotPending as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This request was already answered") from exc

    except ApprovalExpired as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This request expired. Please ask again") from exc
