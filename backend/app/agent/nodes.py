"""The nodes of the planner graph: loading the user's memories, then the model call that answers."""

from datetime import date

import logging

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, RemoveMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime

from app.agent.budget import (
    MODEL_CALL_LIMIT,
    OUTPUT_TOKEN_LIMIT,
    TOOL_CALL_LIMIT,
    Budget,
    add_model_call,
    add_side_call,
    limit_reached,
    new_budget,
    with_limit,
    )
from app.agent.cancellation import stop_if_cancelled
from app.agent.context import PlannerContext
from app.agent.intents import detect_current_intents
from app.agent.prompt import SYSTEM_BASE_INSTRUCTIONS, TOOL_USAGE_INSTRUCTIONS
from app.agent.repair import repaired_history
from app.agent.state import PlannerState
from app.agent.tools.selection import tools_for
from app.db.session import SessionLocal
from app.features.memory.context import describe_memories, describe_memory
from app.features.memory.repository import MemoryRepository
from app.core.config import get_settings
from app.observability.observations import observe_step, update_step
from app.services.llm import llm_service


SYSTEM_PROMPT = f"{SYSTEM_BASE_INSTRUCTIONS}\n{TOOL_USAGE_INSTRUCTIONS}"

log = logging.getLogger(__name__)

MEMORY_LIMIT = 50

READ_MEMORIES_STEP = "read-memories"

LIMIT_REASONS = {
    MODEL_CALL_LIMIT: "it has taken as many steps as one reply may",
    TOOL_CALL_LIMIT: "it has used as many tools as one reply may",
    OUTPUT_TOKEN_LIMIT: "it has written as much as one reply may",
    }

WRAP_UP_NOTE = (
    "Stop here: this reply cannot go on, because {reason}. Do not call any tool. "
    "In two or three short lines, tell the user plainly what you have done so far in this reply and what is still left, "
    "using only what is above. Then offer to carry on if they ask. Do not mention limits, steps, tools or tokens."
    )

FALLBACK_TEXT = "I've done part of this, but couldn't finish it in one go. Ask me to continue and I'll pick up from here."

REPAIR_NODE = "repair_history"
INTENT_NODE = "classify_intents"
MEMORY_NODE = "load_memories"
AGENT_NODE = "agent"
APPROVAL_NODE = "approval_gate"
TOOLS_NODE = "tools"


def describe_user(profile: dict[str, str]) -> str:

    """Write the user's saved basic details as a short block for the system prompt."""

    if not profile:
        return "About the user: no basic details saved yet."

    details = "\n".join(f"- {name}: {value}" for name, value in profile.items())

    return f"About the user (from your memory):\n{details}"


async def repair_history(state: PlannerState) -> dict:

    """Give every unanswered tool call left by a stopped turn a stopped reply, rewriting the saved history only when one is missing."""

    fixed = repaired_history(state["messages"])

    if fixed is None:
        return {}

    log.warning("repaired %s unanswered tool calls in the history", len(fixed) - len(state["messages"]))

    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *fixed]}


async def classify_intents(state: PlannerState) -> dict:

    """Find the new message's intents, and start the turn with no reply flag and a fresh budget that holds the classifier's tokens."""

    intents, answer = await detect_current_intents(state["messages"])

    return {"current_intents": intents, "skip_reply": False, "budget": add_side_call(new_budget(), answer)}


async def load_memories(state: PlannerState, runtime: Runtime[PlannerContext]) -> dict:

    """Read the user's newest active memories into the state."""

    async with observe_step(get_settings(), READ_MEMORIES_STEP, "retriever", {"limit": MEMORY_LIMIT}) as step:

        async with SessionLocal() as session:
            memories = await MemoryRepository(session).active_memories(runtime.context.user_id, limit=MEMORY_LIMIT)

        update_step(step, metadata={"memory_count": len(memories)})

    return {"memories": [describe_memory(memory) for memory in memories]}


async def stream_answer(
    model: Runnable[LanguageModelInput, AIMessage],
    messages: list[AnyMessage],
    ) -> AIMessage | None:

    """Stream one model call to its end and return the whole answer, with its token usage, or None when it sent nothing."""

    answer = None

    async for chunk in model.astream(messages):

        answer = chunk if answer is None else answer + chunk

    return answer


async def wrap_up(
    messages: list[AnyMessage],
    limit: str,
    tools: list[BaseTool],
    ) -> AIMessage:

    """Ask for a short closing reply that says what was done and what is left, with no tool allowed, or fall back to a fixed line."""

    note = SystemMessage(WRAP_UP_NOTE.format(reason=LIMIT_REASONS[limit]))
    model = llm_service.without_acting(tools, get_settings().WRAP_UP_MAX_TOKENS)

    try:
        answer = await stream_answer(model, [*messages, note])

    except Exception:

        log.exception("wrap-up reply failed after %s", limit)

        answer = None

    if answer is None or not answer.content:
        return AIMessageChunk(FALLBACK_TEXT)

    return answer


async def run_agent(state: PlannerState, runtime: Runtime[PlannerContext]) -> dict:

    """Stop if the run was asked to, then stream one model answer or tool request with the tools the turn's intents need, or a closing reply at a limit, and count it."""

    await stop_if_cancelled(runtime.context.run_id)

    system = (
        f"{SYSTEM_PROMPT}\n{describe_user(runtime.context.profile)}\n"
        f"Today's date is {date.today().isoformat()}."
        )

    memory = describe_memories(state.get("memories", []))

    messages = [SystemMessage(system), SystemMessage(memory), *state["messages"]]
    budget: Budget = state.get("budget") or new_budget()
    tools = tools_for(state.get("current_intents", []))

    limit = limit_reached(budget)

    if limit is not None:

        answer = await wrap_up(messages, limit, tools)

        return {"messages": [answer], "budget": with_limit(add_model_call(budget, answer), limit)}

    model = llm_service.with_tools(tools, max_tokens=get_settings().MAX_OUTPUT_TOKENS_PER_CALL)

    answer = await stream_answer(model, messages)

    budget = add_model_call(budget, answer)

    if answer is None:
        return {"messages": [], "budget": budget}

    return {"messages": [answer], "budget": budget}
