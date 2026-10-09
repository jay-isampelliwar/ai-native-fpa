"""The runs routes: start a run for one user message."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_session
from app.features.runs.exceptions import ConversationNotFound, RunAlreadyActive
from app.features.runs.schemas import CreateRunRequest, RunResponse
from app.features.runs.service import RunService


router = APIRouter(prefix="/runs", tags=["runs"])


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
