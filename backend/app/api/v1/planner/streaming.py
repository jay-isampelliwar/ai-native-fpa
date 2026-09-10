"""Server sent events for the chat, so a person reads a reply forming instead of watching a spinner.

The events are the three the frontend already listens for. ``token`` carries the words as the model
writes them, ``done`` carries the finished answer, and ``error`` closes a failed stream with
something a client can act on. ``progress`` is emitted once at the start and nowhere else: it used to
name the node that had just finished, and with a single node there is nothing to narrate between
"thinking" and the answer. It no longer carries a ``skill`` either - there are no skills to name.

Tokens come from LangGraph's ``messages`` stream mode, which taps the model call inside the node
rather than the node's return value. That is the only place the words exist before the node finishes,
so streaming without it would emit one event holding the whole reply.

``done`` repeats the same text the tokens spelled out, and it is the authoritative one. Right now they
are always identical - nothing rewrites the reply between the two - but a client that renders tokens
and then replaces them with ``done`` stays correct when something does, which is what the figure check
did before it was removed and what it will do again.

Errors are emitted as an ``error`` event and then the stream closes normally. An SSE connection that
drops without a terminal event leaves a client unable to tell a failure from a slow answer.
"""

import json
from collections.abc import AsyncIterator

from app.agent.graph import AGENT_NODE
from app.agent.user_data import UserProfile
from app.api.v1.planner.schemas import MessageResponse


def event(name: str, payload: dict) -> str:

    """Format one server sent event, which must end with a blank line to be delivered."""

    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


async def stream_chat(
    graph,
    user_id: int,
    conversation_id: str,
    message: str,
    ) -> AsyncIterator[str]:

    """Run one graph invocation, emitting the model's words as they arrive and the answer at the end."""

    state = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "profile": UserProfile(user_id=user_id),
        "messages": [("user", message)],
    }

    config = {"configurable": {"thread_id": conversation_id}}

    written: list[str] = []

    yield event("progress", {"node": "start", "label": "Thinking"})

    try:
        async for chunk, metadata in graph.astream(state, config=config, stream_mode="messages"):

            if metadata.get("langgraph_node") != AGENT_NODE:
                continue

            text = text_of(chunk)

            if not text:
                continue

            written.append(text)

            yield event("token", {"text": text})

        body = MessageResponse(conversation_id=conversation_id, response="".join(written))

        yield event("done", body.model_dump())

    except Exception as exc:

        yield event("error", {"error": type(exc).__name__, "message": "the request could not be completed"})


def text_of(chunk) -> str:

    """Take the plain text out of one streamed message chunk, ignoring anything that is not prose."""

    content = getattr(chunk, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))

    return ""
