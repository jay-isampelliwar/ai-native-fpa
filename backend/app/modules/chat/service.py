"""Runs one chat turn through the planner graph and turns its tokens into SSE events."""

import json
import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, HumanMessage

from app.agent import graph as planner


log = logging.getLogger(__name__)

THREAD_ID = "default"


def sse_event(event: str, data: dict) -> str:

    """Format one server-sent event with a name and a JSON body."""

    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_chat(message: str) -> AsyncIterator[str]:

    """Send the message to the agent and yield token, done or error events."""

    config = {"configurable": {"thread_id": THREAD_ID}}
    graph_input = {"messages": [HumanMessage(content=message)]}

    try:

        async for chunk, _ in planner.planner_graph.astream(
            graph_input,
            config=config,
            stream_mode="messages",
            ):

            if isinstance(chunk, AIMessageChunk) and chunk.content:
                yield sse_event("token", {"content": chunk.content})

    except Exception:

        log.exception("chat turn failed on thread %s", THREAD_ID)

        yield sse_event("error", {"message": "The agent could not answer. Please try again."})

        return

    yield sse_event("done", {"thread_id": THREAD_ID})
