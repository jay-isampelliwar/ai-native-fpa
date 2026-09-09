from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.v1.planner.schemas import (
    ApprovalRequest,
    ConversationDetail,
    ConversationMessageRead,
    ConversationRead,
    MessageRequest,
    MessageResponse,
)
from app.api.v1.planner.streaming import stream_planner_run
from app.agent import graph as planner
from app.repositories.conversations_repository import conversations_repository

router = APIRouter(prefix="/planner", tags=["planner"])


def to_response(conversation_id: str, state: dict) -> MessageResponse:

    """Narrow finished graph state into the view a client is allowed to see."""

    tools = state.get("tools_used") or []

    return MessageResponse(
        conversation_id=conversation_id,
        correlation_id=correlation_of(state),
        skill=", ".join(dict.fromkeys(tools)) or None,
        status=status_of(state),
        response=state.get("response", ""),
    )


def correlation_of(state: dict) -> str | None:

    """Take the correlation id off whichever shape the context arrived in."""

    context = state.get("context")

    if context is None:
        return None

    return getattr(context, "correlation_id", None) or context.get("correlation_id")


def status_of(state: dict) -> str:

    """Classify the turn for the client, matching what the audit row recorded about it."""

    if state.get("denial_reason"):
        return "refused"

    if state.get("writes_performed"):
        return "completed"

    return "answered" if state.get("response") else "failed"


async def own_conversation(user_id: int, conversation_id: str | None) -> str:

    """Resolve the thread this message belongs to, refusing one that belongs to somebody else."""

    if not conversation_id:
        return f"conv_{uuid4().hex}"

    if await conversations_repository.find(user_id, conversation_id) is None:
        raise HTTPException(status_code=404, detail="no such conversation")

    return conversation_id


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
        pass


async def remember_answer(user_id: int, body: MessageResponse) -> None:

    """Record what the planner replied, leaving the block columns empty while the chat answers in prose."""

    try:
        await conversations_repository.append(
            user_id=user_id,
            conversation_id=body.conversation_id,
            role="planner",
            text=body.response,
            blocks=[],
            skill_name=body.skill,
            status=body.status,
            correlation_id=body.correlation_id,
            evidence_ids=[],
            calculator_versions=[],
        )

    except Exception:
        pass


@router.post("/messages", response_model=MessageResponse)
async def send_message(request: MessageRequest) -> MessageResponse:

    """Start one graph run for a user message and return its answer or the approval it is waiting on."""

    conversation_id = await own_conversation(request.user_id, request.conversation_id)

    await remember_question(request.user_id, conversation_id, request.message)

    state = await planner.planner_graph.ainvoke(
        new_turn(request.user_id, conversation_id, request.message),
        config={"configurable": {"thread_id": conversation_id}},
    )

    body = to_response(conversation_id, state)

    await remember_answer(request.user_id, body)

    return body


@router.post("/approvals", response_model=MessageResponse)
async def decide_approval(request: ApprovalRequest) -> MessageResponse:

    """Report that nothing is awaiting a decision, since the agent applies changes as it makes them."""

    await own_conversation(request.user_id, request.conversation_id)

    return MessageResponse(
        conversation_id=request.conversation_id,
        status="refused",
        response=(
            "There is nothing waiting for your approval. I apply changes as I make them now, so "
            "tell me what to correct and I will do it."
        ),
    )


@router.post("/messages/stream")
async def stream_message(request: MessageRequest) -> StreamingResponse:

    """Run one graph invocation and stream progress events, ending with the complete answer."""

    conversation_id = await own_conversation(request.user_id, request.conversation_id)

    await remember_question(request.user_id, conversation_id, request.message)

    config = {"configurable": {"thread_id": conversation_id}}

    state = new_turn(request.user_id, conversation_id, request.message)

    return StreamingResponse(
        stream_planner_run(planner.planner_graph, state, config, conversation_id, request.user_id),
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
