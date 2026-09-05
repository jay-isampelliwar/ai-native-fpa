"""Server sent events for the chat, so the interface shows progress rather than a spinner.

A planner answer can take several seconds - a routing call, a repository read, a calculator, and
for the investigation skill an agent loop. Returning nothing until all of it finishes makes a
working system feel broken, and the graph already knows what it is doing at each step.

Events are emitted from LangGraph's ``updates`` stream, which yields one entry per node as it
completes. That means the client is told which skill was chosen the moment routing returns,
rather than after the skill has run, and can show the right shell while the figures arrive.

Only node names and finished results cross the wire. The graph's state carries the caller's
scopes, the loaded skill definition and the raw denial reason, none of which a client should see,
so each event is built explicitly rather than by dumping state.

The stream ends with a single ``done`` event carrying the same body the non streaming endpoint
returns. A client can therefore ignore every intermediate event and still be correct, which keeps
the streaming path from becoming a second source of truth about what the answer was.

Errors are emitted as an ``error`` event and then the stream closes normally. An SSE connection
that drops without a terminal event leaves a client unable to tell a failure from a slow answer.

The answer is written to the transcript here rather than in the endpoint, because on this path the
endpoint has already returned by the time there is an answer to record. The question was recorded
before the response was constructed, so the two halves of a turn are written from two places - which
is the cost of streaming, and cheaper than a second code path that recomputes the body.
"""

import json
from collections.abc import AsyncIterator

import orjson

from app.api.v1.planner.schemas import MessageResponse

PROGRESS_LABELS = {
    "authenticate_context": "Checking your session",
    "route_request": "Working out what you are asking",
    "load_skill_definition": "Loading the right skill",
    "check_permissions": "Checking permissions",
    "execute_skill": "Reading your records",
    "validate_skill_result": "Verifying the result",
    "request_approval": "Waiting for your approval",
    "controlled_write": "Applying the approved change",
    "write_audit_record": "Recording what happened",
    "respond": "Composing the answer",
}


def event(name: str, payload: dict) -> str:

    """Format one server sent event, which must end with a blank line to be delivered."""

    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


async def stream_planner_run(
    graph,
    state: dict,
    config: dict,
    conversation_id: str,
    user_id: int,
    ) -> AsyncIterator[str]:

    """Run the graph, emitting one progress event per completed node and one final result."""

    final_state: dict = {}

    try:
        async for update in graph.astream(state, config=config, stream_mode="updates"):

            for node_name, node_state in update.items():

                if node_name == "__interrupt__":
                    continue

                final_state.update(node_state or {})

                yield event(
                    "progress",
                    {
                        "node": node_name,
                        "label": PROGRESS_LABELS.get(node_name, node_name),
                        "skill": final_state.get("skill_name"),
                    },
                )

        snapshot = await graph.aget_state(config)

        body = build_body(conversation_id, snapshot)

        await remember_answer(user_id, body)

        yield event("done", orjson.loads(body.model_dump_json()))

    except Exception as exc:

        yield event("error", {"error": type(exc).__name__, "message": "the request could not be completed"})


async def remember_answer(user_id: int, body: MessageResponse) -> None:

    """Record the streamed answer through the same helper the non streaming path uses."""

    from app.api.v1.planner.router import remember_answer as record

    await record(user_id, body)


def build_body(conversation_id: str, snapshot) -> MessageResponse:

    """Build the same response the non streaming endpoint returns, from the finished graph state."""

    from app.api.v1.planner.router import to_response

    values = dict(snapshot.values)

    if snapshot.interrupts:
        values["__interrupt__"] = snapshot.interrupts

    return to_response(conversation_id, values)
