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

Every turn is written to the transcript tables as it happens. The checkpointer holds the machine
state of the latest run and was never a history: it is encrypted, shaped for resuming a paused graph,
and pruned on its own schedule, so a person who closed the tab had lost the conversation. The
question is recorded before the graph runs, which means a run that fails still leaves evidence of
what was asked rather than a gap.

Recording never fails a request. The answer has already been computed by the time it is written, and
refusing to return it because a transcript row would not insert would turn a logging problem into an
outage. A failed write is logged and the turn is simply missing from the history.

The three ``/conversations`` endpoints are reads over those tables, plus the one delete this service
offers anywhere. A chat a person chose to discard is theirs to discard; nothing financial and no
audit record is reachable through it.
"""

from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from app.api.v1.planner.schemas import (
    ApprovalRequest,
    ConversationDetail,
    ConversationMessageRead,
    ConversationRead,
    MessageRequest,
    MessageResponse,
    PendingApproval,
)
from app.api.v1.planner.streaming import stream_planner_run
from app.graphs.orchestrator.graph import get_planner_graph
from app.repositories.conversations_repository import conversations_repository
from app.ui.blocks import ApprovalCardBlock, FieldChange

log = structlog.get_logger(__name__)

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


async def remember_question(user_id: int, conversation_id: str, message: str) -> None:

    """Record what was asked before the graph runs, so a failed run still leaves the question."""

    try:
        await conversations_repository.append(
            user_id=user_id,
            conversation_id=conversation_id,
            role="user",
            text=message,
        )

    except Exception:

        log.warning("transcript.question_not_recorded", conversation_id=conversation_id, exc_info=True)


async def remember_answer(user_id: int, body: MessageResponse) -> None:

    """Record what the planner replied, including the blocks the client was actually shown."""

    try:
        await conversations_repository.append(
            user_id=user_id,
            conversation_id=body.conversation_id,
            role="planner",
            text=body.response,
            blocks=[block.model_dump(mode="json") for block in body.blocks],
            skill_name=body.skill,
            status=body.status,
            correlation_id=body.correlation_id,
            evidence_ids=body.evidence_ids,
            calculator_versions=body.calculator_versions,
        )

    except Exception:

        log.warning("transcript.answer_not_recorded", conversation_id=body.conversation_id, exc_info=True)


@router.post("/messages", response_model=MessageResponse)
async def send_message(request: MessageRequest) -> MessageResponse:

    """Start one graph run for a user message and return its answer or the approval it is waiting on."""

    conversation_id = request.conversation_id or f"conv_{uuid4().hex}"

    await remember_question(request.user_id, conversation_id, request.message)

    state = await get_planner_graph().ainvoke(
        {
            "user_id": request.user_id,
            "conversation_id": conversation_id,
            "user_message": request.message,
        },
        config={"configurable": {"thread_id": conversation_id}},
    )

    body = to_response(conversation_id, state)

    await remember_answer(request.user_id, body)

    return body


@router.post("/approvals", response_model=MessageResponse)
async def decide_approval(request: ApprovalRequest) -> MessageResponse:

    """Resume the paused run on this conversation with the human's decision, never starting a new one."""

    await remember_question(
        request.user_id,
        request.conversation_id,
        "Approved." if request.decision == "approve" else "Rejected.",
    )

    state = await get_planner_graph().ainvoke(
        Command(resume=request.decision),
        config={"configurable": {"thread_id": request.conversation_id}},
    )

    body = to_response(request.conversation_id, state)

    await remember_answer(request.user_id, body)

    return body


@router.post("/messages/stream")
async def stream_message(request: MessageRequest) -> StreamingResponse:

    """Run one graph invocation and stream progress events, ending with the complete answer."""

    conversation_id = request.conversation_id or f"conv_{uuid4().hex}"

    await remember_question(request.user_id, conversation_id, request.message)

    config = {"configurable": {"thread_id": conversation_id}}

    state = {
        "user_id": request.user_id,
        "conversation_id": conversation_id,
        "user_message": request.message,
    }

    return StreamingResponse(
        stream_planner_run(get_planner_graph(), state, config, conversation_id, request.user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[ConversationRead])
async def list_conversations(user_id: int, limit: int = 50) -> list[ConversationRead]:

    """List this user's chat sessions, most recently spoken to first."""

    rows = await conversations_repository.sessions(user_id, limit)

    return [ConversationRead.model_validate(row, from_attributes=True) for row in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def read_conversation(conversation_id: str, user_id: int) -> ConversationDetail:

    """Reopen one conversation, returning its turns in the order they happened."""

    conversation = await conversations_repository.find(user_id, conversation_id)

    if conversation is None:
        raise HTTPException(status_code=404, detail="no such conversation")

    messages = await conversations_repository.transcript(user_id, conversation_id)

    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
        messages=[to_message_read(row) for row in messages],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def discard_conversation(conversation_id: str, user_id: int) -> None:

    """Delete one conversation and every turn in it, the only deletion this service offers."""

    if not await conversations_repository.discard(user_id, conversation_id):
        raise HTTPException(status_code=404, detail="no such conversation")


def to_message_read(row) -> ConversationMessageRead:

    """Narrow one stored turn into the client view, re-validating its blocks through the live union."""

    return ConversationMessageRead(
        id=row.id,
        position=row.position,
        role=row.role,
        text=row.text,
        blocks=row.blocks,
        skill=row.skill_name,
        status=row.status,
        correlation_id=row.correlation_id,
        evidence_ids=list(row.evidence_ids),
        calculator_versions=list(row.calculator_versions),
        created_at=row.created_at,
    )
