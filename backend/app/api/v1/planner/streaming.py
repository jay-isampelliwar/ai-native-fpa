"""Server sent events for the chat, so the interface shows progress rather than a spinner.

A planner answer can take several seconds - a routing call, a repository read, a calculator, and
for the investigation skill an agent loop. Returning nothing until all of it finishes makes a
working system feel broken, and the graph already knows what it is doing at each step.

Events come from two of LangGraph's stream modes at once. ``updates`` yields one entry per node as
it completes, so the client is told which skill was chosen the moment routing returns rather than
after the skill has run. ``custom`` carries whatever a skill writes from inside its own run, which
is how a tool call several frames deep - inside an agent loop, inside the conversation node - reaches
the client at all. Without it the longest part of the longest answer is a single unchanging label.

Four nodes emit nothing. Authenticating, loading a definition, checking permissions and writing the
audit record are steps in this system's own bookkeeping, and a person waiting on an answer about
their money does not need to be told that permissions were checked - it reads as busywork and it
buries the two lines that are actually about them. They still run, are still audited and still refuse
what they should; they are simply not narrated.

The answer arrives twice, and the second one is the truth. ``token`` events carry the words as the
model writes them, so a person reads a reply forming instead of watching a spinner for several
seconds; the closing ``done`` event carries the finished body, after the figure check has decided
whether that reply survives. A client renders the tokens as they come and replaces them with what
``done`` says, which is identical except in the case the check exists for.

"Thinking" is emitted before the graph starts rather than when a node finishes. ``updates`` fires on
completion, so a label attached to the conversation node would arrive after the work it describes -
after the tool events it emitted, which is exactly backwards from what a person is watching for.

The skills name themselves as they are called, rather than being named here. ``updates`` fires when a
node completes, and the whole conversation is one node - so labelling it could only say "thinking"
before and "done" after, with the several seconds in between unexplained. Each skill tool writes its
own line as it starts, which is why the interesting part of a long answer is visible while it
happens.

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

SILENT = {
    "authenticate_context",
    "agent",
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

    yield event("progress", {"node": "start", "label": "Thinking", "skill": None})

    try:
        async for chunk in graph.astream(state, config=config, stream_mode="updates"):

            for node_name, node_state in chunk.items():

                final_state.update(node_state or {})

                if node_name in SILENT:
                    continue

                yield event(
                    "progress",
                    {"node": node_name, "label": node_name, "skill": None},
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

    return to_response(conversation_id, dict(snapshot.values))
