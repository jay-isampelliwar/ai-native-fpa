"""One endpoint: a streaming chat turn.

There is one endpoint because there is one thing the agent can do right now - answer a message in
prose. ``/messages``, ``/approvals`` and the three ``/conversations`` reads were the surface of a
planner that routed to skills, paused writes for a human decision and kept its own transcript
tables. None of that is in the graph any more, so keeping their routes would be advertising
behaviour that no longer exists. They come back one at a time with the features that need them.

Streaming is the surviving shape rather than the plain POST, because it is the strictly larger one: a
client that ignores every ``token`` event and reads only the closing ``done`` event gets exactly what
the plain endpoint returned. Keeping both would mean two paths to the same answer, and the shorter one
makes a person watch a spinner for several seconds.

Nothing is written to the ``conversations`` tables on this path yet. The checkpointer keyed by
``conversation_id`` is what carries the earlier messages of a thread, which is enough for the chat to
follow a conversation; a transcript a person can reopen weeks later is a separate feature and needs
the reads that went with it. ``app.repositories.conversations_repository`` is left in the tree for
that, unused for now.

A conversation id is no longer checked against its owner, and that is a real loss stated plainly. The
check read the conversation row this path no longer writes, so it could only have rejected every
second message. It has to return with the transcript, because the id is the graph's thread id - a
request carrying somebody else's id reads somebody else's messages.
"""

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
        stream_chat(planner.planner_graph, request.user_id, conversation_id, request.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
