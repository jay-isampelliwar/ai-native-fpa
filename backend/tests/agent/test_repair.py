"""Tests for repairing a history left with unanswered tool calls by a stopped turn, alone and inside a graph."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent.context import PlannerContext
from app.agent.nodes import REPAIR_NODE, repair_history
from app.agent.repair import INTERRUPTED, repaired_history
from app.agent.state import PlannerState
from app.features.runs.worker import update_messages


def asks(*call_ids: str) -> AIMessage:

    """An assistant message asking for one tool call per id."""

    return AIMessage("", tool_calls=[{"name": "add_loan", "args": {}, "id": call_id} for call_id in call_ids])


def answer(call_id: str) -> ToolMessage:

    """A tool reply for one call id."""

    return ToolMessage("saved", tool_call_id=call_id, name="add_loan")


def shape(messages: list) -> list[str]:

    """Each message as its type, with the call id for a tool reply."""

    return [f"tool:{message.tool_call_id}" if isinstance(message, ToolMessage) else message.type for message in messages]


def test_complete_history_needs_no_repair() -> None:

    """Every call answered means nothing to fix."""

    assert repaired_history([HumanMessage("hi"), asks("a"), answer("a"), AIMessage("Saved.")]) is None


def test_stopped_call_gets_a_reply_before_the_new_message() -> None:

    """A call cut off by a stop gets its reply right after the request, before the user's next message."""

    fixed = repaired_history([HumanMessage("add my loan"), asks("a", "b"), answer("a"), HumanMessage("hi")])

    assert shape(fixed) == ["human", "ai", "tool:a", "tool:b", "human"]

    stopped = fixed[3]

    assert stopped.status == "error"
    assert stopped.artifact["status"] == "retryable_error"
    assert stopped.artifact["error_code"] == INTERRUPTED
    assert stopped.name == "add_loan"


def test_stopped_call_at_the_end_is_answered() -> None:

    """A call cut off as the last message is answered at the end."""

    assert shape(repaired_history([HumanMessage("add my loan"), asks("a")])) == ["human", "ai", "tool:a"]


def build():

    """The repair node then a node that keeps what it was shown, on an in-memory checkpointer."""

    seen: list = []

    async def look(state: PlannerState) -> dict:

        """Keep the history the next node gets."""

        seen.extend(state["messages"])

        return {}

    builder = StateGraph(PlannerState, context_schema=PlannerContext)

    builder.add_node(REPAIR_NODE, repair_history)
    builder.add_node("look", look)

    builder.add_edge(START, REPAIR_NODE)
    builder.add_edge(REPAIR_NODE, "look")
    builder.add_edge("look", END)

    return builder.compile(checkpointer=InMemorySaver()), seen


async def test_repair_node_fixes_the_saved_history() -> None:

    """A thread left broken by a stop is fixed in the checkpoint on the next message, in the right order."""

    graph, seen = build()
    config = {"configurable": {"thread_id": "broken"}}
    context = PlannerContext(user_id=1)

    await graph.aupdate_state(config, {"messages": [HumanMessage("add my loan"), asks("a")]}, as_node="look")

    await graph.ainvoke({"messages": [HumanMessage("hi")]}, config, context=context)

    saved = (await graph.aget_state(config)).values["messages"]

    assert shape(seen) == ["human", "ai", "tool:a", "human"]
    assert shape(saved) == ["human", "ai", "tool:a", "human"]

    await graph.ainvoke({"messages": [HumanMessage("thanks")]}, config, context=context)

    assert len((await graph.aget_state(config)).values["messages"]) == 5


def test_worker_ignores_the_repair_rewrite() -> None:

    """The repair's rewrite of old history is not taken as new tool steps, while other nodes' messages are."""

    update = {REPAIR_NODE: {"messages": [asks("a"), answer("a")]}, "agent": {"messages": [AIMessage("Hi")]}}

    assert [message.content for message in update_messages(update)] == ["Hi"]
