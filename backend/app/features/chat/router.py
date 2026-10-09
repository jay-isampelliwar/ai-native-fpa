"""The chat route that streams the planner agent's reply."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.features.chat.schemas import ChatRequest
from app.features.chat.service import stream_chat


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(body: ChatRequest) -> StreamingResponse:

    """Stream the agent's answer to one message as server-sent events."""

    return StreamingResponse(
        stream_chat(body.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )
