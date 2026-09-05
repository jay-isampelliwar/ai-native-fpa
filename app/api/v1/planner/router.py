"""The single HTTP entry point into the planner, and the only way a request starts a run.

There is one endpoint for messages and one for approvals, not one per skill. Which skill
runs is decided inside the graph by ``route_request`` and then checked against the
registry, so a client cannot name a skill and cannot reach one that routing would not
have chosen. Exposing a route per skill would hand that choice to whoever calls the API
and quietly remove the layer this design exists to keep.

``conversation_id`` is the LangGraph thread id. A run that pauses for approval leaves its
state under that id, and ``approve`` resumes it with ``Command(resume=...)`` rather than
starting a new run, which is why the approved change is the exact one the user saw
instead of whatever a second classification would produce.

An interrupted run is a normal response, not an error. LangGraph reports it in
``__interrupt__``, and this module turns that into a ``pending_approval`` block so the
client can render the before and after and ask the question. The write has not happened
and will not until the approval endpoint is called.

The user id arrives in the request body because Phase 1 has no tokens. That is the seam
where authentication lands later: replace the body field with a verified credential and
every layer below this file is untouched.

``/messages/stream`` runs the same graph as ``/messages`` and returns the same final body. It
exists so the interface can show which step is running rather than a spinner, and a client that
ignores every intermediate event still gets a correct answer from the terminal one.
"""

from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from app.api.v1.planner.schemas import (
    ApprovalRequest,
    MessageRequest,
    MessageResponse,
    PendingApproval,
)
from app.api.v1.planner.streaming import stream_planner_run
from app.graphs.orchestrator.graph import get_planner_graph
from app.ui.blocks import ApprovalCardBlock, FieldChange

router = APIRouter(prefix="/planner", tags=["planner"])


def to_response(conversation_id: str, state: dict) -> MessageResponse:

    """Narrow finished or paused graph state into the view a client is allowed to see."""

    interrupts = state.get("__interrupt__")

    if interrupts:
        payload = interrupts[0].value

        return MessageResponse(
            conversation_id=conversation_id,
            skill=payload.get("skill"),
            status="awaiting_approval",
            response="This change needs your approval before anything is updated.",
            blocks=[approval_card(conversation_id, payload)],
            evidence_ids=payload.get("evidence_ids", []),
            pending_approval=PendingApproval(
                conversation_id=conversation_id,
                skill=payload.get("skill"),
                summary=payload.get("message", ""),
                evidence_ids=payload.get("evidence_ids", []),
                expires_in_seconds=payload.get("expires_in_seconds", 0),
            ),
        )

    result = state.get("result")
    context = state.get("context")

    return MessageResponse(
        conversation_id=conversation_id,
        correlation_id=context.correlation_id if context else None,
        skill=state.get("skill_name"),
        status=result.status if result else "refused",
        response=state.get("response", ""),
        blocks=result.blocks if result else [],
        evidence_ids=result.evidence_ids if result else [],
        calculator_versions=result.calculator_versions if result else [],
    )


def approval_card(conversation_id: str, payload: dict) -> ApprovalCardBlock:

    """Render an interrupted run's proposal as the card the user approves or rejects inline."""

    changes = [
        FieldChange(label=change.get("label", ""), before=change.get("before"), after=change.get("after", ""))
        for change in payload.get("changes", [])
    ]

    return ApprovalCardBlock(
        title=payload.get("title") or payload.get("message", "Approve this change?"),
        changes=changes,
        approval_id=conversation_id,
        expires_in_seconds=payload.get("expires_in_seconds", 0),
        evidence_ids=payload.get("evidence_ids", []),
    )


@router.post("/messages", response_model=MessageResponse)
async def send_message(request: MessageRequest) -> MessageResponse:

    """Start one graph run for a user message and return its answer or the approval it is waiting on."""

    conversation_id = request.conversation_id or f"conv_{uuid4().hex}"

    state = await get_planner_graph().ainvoke(
        {
            "user_id": request.user_id,
            "conversation_id": conversation_id,
            "user_message": request.message,
        },
        config={"configurable": {"thread_id": conversation_id}},
    )

    return to_response(conversation_id, state)


@router.post("/approvals", response_model=MessageResponse)
async def decide_approval(request: ApprovalRequest) -> MessageResponse:

    """Resume the paused run on this conversation with the human's decision, never starting a new one."""

    state = await get_planner_graph().ainvoke(
        Command(resume=request.decision),
        config={"configurable": {"thread_id": request.conversation_id}},
    )

    return to_response(request.conversation_id, state)


@router.post("/messages/stream")
async def stream_message(request: MessageRequest) -> StreamingResponse:

    """Run one graph invocation and stream progress events, ending with the complete answer."""

    conversation_id = request.conversation_id or f"conv_{uuid4().hex}"

    config = {"configurable": {"thread_id": conversation_id}}

    state = {
        "user_id": request.user_id,
        "conversation_id": conversation_id,
        "user_message": request.message,
    }

    return StreamingResponse(
        stream_planner_run(get_planner_graph(), state, config, conversation_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
