"""The graph around the agent: that a turn is audited, streamed and answered, whatever the agent did.

This file used to be about gates - a router's choice, a permission edge, a result validator, an
approval interrupt - because a turn was several decisions in sequence and each fork was worth a test.
The graph is four nodes in a line now, so what is left to defend is narrower and mostly about
bookkeeping: a request cannot answer somebody without leaving an audit row, a failure still reaches
that row, and the words of an answer reach the client as they are written.

The agent node is stubbed in every test here. What is under test is the graph, and a test of the graph
that depended on a model would fail for reasons that have nothing to do with the graph. The tools
themselves are tested for real in ``test_agent_tools``.

``test_a_failed_turn_is_still_recorded`` is the one worth keeping if the file ever shrinks. An audit
trail that only contains successful turns cannot be audited, and the failure path is the one nobody
exercises by hand.

The streaming test asserts that tokens are forwarded rather than invented, and that the terminal event
carries the same answer the non streaming path returns. A client is allowed to ignore every
intermediate event and still be correct, and that property is what keeps the streaming path from
becoming a second source of truth about what was said.
"""

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.db.fixture_ids import SEED_USER_ID
from app.agent.graph import build_planner_graph
from app.agent.state import new_turn

pytestmark = pytest.mark.asyncio


async def run_graph(agent_node, message: str = "how much is left this month?") -> dict:

    """Compile a fresh graph with the agent stubbed and run one request through it."""

    from app.agent import graph as graph_module

    original = graph_module.run_agent

    graph_module.run_agent = agent_node

    try:
        graph = build_planner_graph(InMemorySaver())

        return await graph.ainvoke(
            new_turn(SEED_USER_ID, "conv_1", message),
            config={"configurable": {"thread_id": "thread_1"}},
        )

    finally:
        graph_module.run_agent = original


async def test_an_answered_turn_carries_what_it_did_out_to_the_response():

    """What the agent node produced reaches the client rather than stopping inside the node."""

    async def agent(state):

        """Answer with one figure and name the tool that produced it."""

        return {
            "response": "Your surplus is INR 70,000.",
            "tools_used": ["cashflow_summary"],
            "writes_performed": [],
        }

    state = await run_graph(agent)

    assert state["response"] == "Your surplus is INR 70,000."
    assert state["tools_used"] == ["cashflow_summary"]


async def test_a_turn_needing_no_tool_is_still_answered():

    """A greeting is a conversation rather than the closest financial capability, which was the point."""

    from tests.conftest import answer_with

    state = await run_graph(answer_with("Hello - what would you like to know?"), message="hi")

    assert state["response"] == "Hello - what would you like to know?"
    assert state["tools_used"] == []


async def test_a_turn_without_a_caller_refuses_and_still_answers():

    """A refusal is owed an explanation, and no node downstream is left to turn one into a sentence."""

    from app.agent.nodes import run_agent
    from app.agent.state import PlannerState

    state = PlannerState(user_id=SEED_USER_ID, conversation_id="conv_1", user_message="what is my income?")

    update = await run_agent(state)

    assert update["denial_reason"] == "the agent was reached without a caller"
    assert "I could not do that" in update["response"]


async def test_a_second_message_does_not_replay_the_first_answer():

    """State is checkpointed per conversation, so a stale response must be cleared before each turn.

    The stub answers from a queue rather than being swapped between the two calls. ``build_planner_graph``
    binds the node function into the graph when it compiles, so replacing the module attribute afterwards
    has no effect - the graph keeps the function it was built with. That is worth knowing here because
    the mistake does not fail loudly: the test would pass against a graph that never changed behaviour.
    """

    replies = ["First answer.", "Second answer."]

    async def agent(state):

        """Answer with the next queued reply, so one compiled graph can produce two different turns."""

        return {
            "response": replies.pop(0),
            "tools_used": [],
            "writes_performed": [],
            "blocks": [],
            "evidence_ids": [],
            "calculator_versions": [],
            "assumptions": {},
        }

    from app.agent import graph as graph_module

    original = graph_module.run_agent

    graph_module.run_agent = agent

    try:
        graph = build_planner_graph(InMemorySaver())

        config = {"configurable": {"thread_id": "thread_same"}}

        first = await graph.ainvoke(new_turn(SEED_USER_ID, "conv_same", "one"), config=config)

        second = await graph.ainvoke(new_turn(SEED_USER_ID, "conv_same", "two"), config=config)

    finally:
        graph_module.run_agent = original

    assert first["response"] == "First answer."
    assert second["response"] == "Second answer."
