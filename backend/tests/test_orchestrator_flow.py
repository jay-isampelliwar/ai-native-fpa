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


def recorded(monkeypatch) -> list:

    """Capture every audit record the run writes, without needing the audit table."""

    from app.audit import recorder as recorder_module

    written = []

    async def capture(record):
        written.append(record)

    monkeypatch.setattr(recorder_module.recorder, "persist", capture)

    return written


async def test_an_answered_turn_carries_its_evidence_out_to_the_response(monkeypatch):

    """What the tools produced reaches the client rather than stopping inside the agent node."""

    recorded(monkeypatch)

    async def agent(state):

        """Answer with one figure, its evidence and the calculator behind it."""

        return {
            "response": "Your surplus is INR 70,000.",
            "tools_used": ["cashflow_summary"],
            "writes_performed": [],
            "blocks": [],
            "evidence_ids": ["inc_1", "exp_1"],
            "calculator_versions": ["cashflow.v1"],
            "assumptions": {},
        }

    state = await run_graph(agent)

    assert state["response"] == "Your surplus is INR 70,000."
    assert state["evidence_ids"] == ["inc_1", "exp_1"]
    assert state["calculator_versions"] == ["cashflow.v1"]


async def test_a_turn_needing_no_tool_is_still_answered(monkeypatch):

    """A greeting is a conversation rather than the closest financial capability, which was the point."""

    from tests.conftest import answer_with

    recorded(monkeypatch)

    state = await run_graph(answer_with("Hello - what would you like to know?"), message="hi")

    assert state["response"] == "Hello - what would you like to know?"
    assert state["tools_used"] == []
    assert state["blocks"] == []


async def test_every_turn_leaves_an_audit_row(monkeypatch):

    """A request cannot answer a person without a trail, so the audit node runs before responding."""

    from tests.conftest import answer_with

    written = recorded(monkeypatch)

    await run_graph(answer_with("Done.", tools=["list_income"]))

    assert len(written) == 1
    assert written[0].user_id == SEED_USER_ID
    assert written[0].correlation_id.startswith("req_")


async def test_the_audit_row_names_the_tools_and_the_changes(monkeypatch):

    """The trail says what a turn looked at and what it altered, since no single skill is named now."""

    from tests.conftest import answer_with

    written = recorded(monkeypatch)

    await run_graph(
        answer_with(
            "Updated your rent.",
            tools=["list_expenses", "update_record"],
            writes=["changed expense exp_1 amount to INR 40,000"],
        )
    )

    record = written[0]

    assert record.skill_name == "list_expenses"
    assert "list_expenses, update_record" in record.route_reason
    assert "changed expense" in record.route_reason
    assert record.write_performed is True
    assert record.result_status == "completed"


async def test_a_read_only_turn_is_not_recorded_as_a_write(monkeypatch):

    """A turn that changed nothing must not look like one that did, or the trail is worthless."""

    from tests.conftest import answer_with

    written = recorded(monkeypatch)

    await run_graph(answer_with("You have three SIPs.", tools=["list_sips"]))

    assert written[0].write_performed is False
    assert written[0].result_status == "answered"


async def test_a_failed_turn_is_still_recorded_and_still_answers(monkeypatch):

    """A refusal is an outcome worth keeping, and the person is owed an explanation either way."""

    written = recorded(monkeypatch)

    async def refusing(state):

        """Report that the turn could not proceed, the way the agent node does without a caller."""

        return {"denial_reason": "the agent was reached without a caller"}

    state = await run_graph(refusing)

    assert "I could not do that" in state["response"]
    assert written[0].result_status == "refused"
    assert written[0].permission_granted is False


async def test_a_second_message_does_not_replay_the_first_answer(monkeypatch):

    """State is checkpointed per conversation, so a stale response must be cleared before each turn.

    The stub answers from a queue rather than being swapped between the two calls. ``build_planner_graph``
    binds the node function into the graph when it compiles, so replacing the module attribute afterwards
    has no effect - the graph keeps the function it was built with. That is worth knowing here because
    the mistake does not fail loudly: the test would pass against a graph that never changed behaviour.
    """

    recorded(monkeypatch)

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


async def test_the_words_of_an_answer_are_forwarded_as_they_are_written(monkeypatch):

    """A person should read a reply forming rather than watch a spinner, so the node streams."""

    from app.agent import nodes

    class StreamingAgent:

        """Answers in pieces, the way the real agent does when something is listening."""

        async def astream(self, payload, stream_mode=None, config=None):

            """Emit two pieces from the answer node and one from a tool, then the finished state."""

            from langchain_core.messages import AIMessage

            yield "messages", (AIMessage(content="Your income "), {"langgraph_node": "model"})
            yield "messages", (AIMessage(content="is INR 226,000."), {"langgraph_node": "model"})
            yield "messages", (AIMessage(content="reading a prompt"), {"langgraph_node": "tools"})
            yield "values", {"messages": [AIMessage(content="Your income is INR 226,000.")]}

    written: list[dict] = []

    finished = await nodes.speak(StreamingAgent(), [("user", "what is my income?")], written.append)

    tokens = [line["token"] for line in written if "token" in line]

    assert tokens == ["Your income ", "is INR 226,000."]
    assert nodes.final_text(finished) == "Your income is INR 226,000."


async def test_a_reply_quoting_a_figure_no_tool_returned_is_set_aside():

    """The figure check is what makes "quote, never compute" a rule rather than a request."""

    from app.agent.state import RunLog
    from app.agent.nodes import settle

    log = RunLog()

    log.returned = ['{"amount": "10000.00"}']

    kept = settle("Your SIP is INR 10,000.", log, "what is my sip?", "")

    set_aside = settle("Your SIPs total INR 18,000.", log, "what is my sip?", "")

    assert kept == "Your SIP is INR 10,000."
    assert "could not trace" in set_aside
