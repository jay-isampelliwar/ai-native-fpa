"""Tests for picking the agent's tools from the turn's intents."""

from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.runtime import Runtime

from app.agent import nodes
from app.agent.context import PlannerContext
from app.agent.intents import (
    ADD_DATA,
    ALLOWED_INTENTS,
    DELETE_DATA,
    GENERAL_QUESTION,
    GOAL_CHECK,
    SIMULATION,
    VIEW_DATA,
    )
from app.agent.nodes import run_agent
from app.agent.tools import ALL_TOOLS
from app.agent.tools.selection import ALWAYS_TOOLS, TOOLS_BY_INTENT, tools_for


ALL_NAMES = [tool.name for tool in ALL_TOOLS]


def names(intents: list[str]) -> list[str]:

    """The names of the tools picked for these intents."""

    return [tool.name for tool in tools_for(intents)]


def test_every_tool_is_reachable_and_every_name_is_real() -> None:

    """Each of the 22 tools is in some intent group, and every name in the map is a real tool."""

    mapped = set(ALWAYS_TOOLS).union(*TOOLS_BY_INTENT.values())

    assert mapped == set(ALL_NAMES)


def test_every_intent_has_a_group() -> None:

    """Every intent but the general one has its own group, so none falls back to all tools by accident."""

    assert set(TOOLS_BY_INTENT) == set(ALLOWED_INTENTS) - {GENERAL_QUESTION}


def test_one_intent_gets_its_tools_and_the_always_set() -> None:

    """A delete gets only delete_record plus the two tools the prompt always needs, in ALL_TOOLS order."""

    assert names([DELETE_DATA]) == ["get_missing_sections", "list_records", "delete_record"]
    assert names([VIEW_DATA]) == ["get_missing_sections", "list_records", "get_portfolio_exposure", "web_search"]


def test_several_intents_get_the_union_once() -> None:

    """Two intents get both groups, with a tool in both sent only once."""

    picked = names([GOAL_CHECK, SIMULATION])

    assert set(picked) == {"get_missing_sections", "list_records", "check_goal_progress", "link_asset_to_goal", "add_goal", "set_planning_rate", "open_form"}
    assert len(picked) == len(set(picked))


@pytest.mark.parametrize("intents", [[GENERAL_QUESTION], [], [ADD_DATA, GENERAL_QUESTION], ["BANK_BALANCE"]])
def test_general_empty_or_unknown_gets_all_tools(intents: list[str]) -> None:

    """A general question, no intents, or a name the map does not know gets every tool."""

    assert names(intents) == ALL_NAMES


async def test_agent_is_given_only_the_picked_tools(monkeypatch: pytest.MonkeyPatch) -> None:

    """run_agent binds the tools for the state's intents, and all tools when the state has none."""

    bound: list[list[str]] = []

    class Answerer:

        """A model that answers in one line."""

        async def astream(self, messages: list) -> Any:

            """Answer at once."""

            yield AIMessageChunk("Done.")

    def with_tools(
        tools: list,
        model: str | None = None,
        max_tokens: int | None = None,
        ) -> Answerer:

        """Remember the tools the agent bound."""

        bound.append([tool.name for tool in tools])

        return Answerer()

    monkeypatch.setattr(nodes.llm_service, "with_tools", with_tools)

    runtime = Runtime(context=PlannerContext(user_id=1))

    await run_agent({"messages": [HumanMessage("Delete my HDFC loan")], "current_intents": [DELETE_DATA]}, runtime)
    await run_agent({"messages": [HumanMessage("hi")]}, runtime)

    assert bound == [["get_missing_sections", "list_records", "delete_record"], ALL_NAMES]
