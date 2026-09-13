

from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.v1.planner.schemas import MessageRequest
from app.api.v1.planner.streaming import stream_chat
from app.agent import graph as planner

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/messages/stream")
async def stream_message(request: MessageRequest) -> StreamingResponse:

    """Run one graph invocation for this message and stream the answer as the model writes it."""

    conversation_id = request.conversation_id or f"conv_{uuid4().hex}"

    return StreamingResponse(
        stream_chat(
            planner.planner_graph,
            request.user_id,
            conversation_id,
            request.message,
            request.import_ids,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
