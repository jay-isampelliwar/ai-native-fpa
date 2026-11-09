"""Tests for finding a message's intents: the keyword rules, the intent model with a fake, the fallback, and the graph node."""

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import intents
from app.agent.intents import (
    ADD_DATA,
    DELETE_DATA,
    FALLBACK_INTENTS,
    GOAL_CHECK,
    SIMULATION,
    VIEW_DATA,
    IntentResult,
    classify_with_model,
    detect_current_intents,
    is_simple,
    match_rules,
    )
from app.agent.nodes import classify_intents
from app.core.config import get_settings


USAGE = {"input_tokens": 120, "output_tokens": 8, "total_tokens": 128}


class FakeIntentModel:

    """Stands in for the intent model chain: remembers what it was shown and answers with fixed intents."""

    def __init__(
        self,
        found: list[str] | None,
        delay: float = 0,
        ) -> None:

        """Keep the intents to answer with, None for an answer that could not be read, and how long to wait."""

        self.found = found
        self.delay = delay
        self.seen: list = []
        self.tags: list[str] = []

    def with_structured_output(
        self,
        schema: Any,
        **kwargs: Any,
        ) -> "FakeIntentModel":

        """Return the same fake, as the real model returns a chain."""

        return self

    def model_copy(self, update: dict[str, Any]) -> "FakeIntentModel":

        """Remember the name the model copy was given."""

        self.name = update.get("name")

        return self

    def with_config(self, tags: list[str]) -> "FakeIntentModel":

        """Remember the tags the chain was given."""

        self.tags = tags

        return self

    async def ainvoke(self, messages: list) -> dict[str, Any]:

        """Answer in the include_raw shape, after the delay."""

        self.seen = messages

        await asyncio.sleep(self.delay)

        parsed = None if self.found is None else IntentResult.model_construct(intents=self.found)

        return {"raw": AIMessage("", usage_metadata=USAGE), "parsed": parsed, "parsing_error": None}


def use_model(
    monkeypatch: pytest.MonkeyPatch,
    model: FakeIntentModel,
    ) -> None:

    """Put back the real classifier, the shared fixture removed it, and point it at the fake model."""

    monkeypatch.setattr(intents, "classify_with_model", classify_with_model)
    monkeypatch.setattr(intents.llm_service, "get_model", lambda name=None: model)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Delete my HDFC home loan", [DELETE_DATA]),
        ("Show me my goals", [VIEW_DATA]),
        ("Am I on track for retirement?", [GOAL_CHECK]),
        ("What if I spend ₹5,000 more each month?", [SIMULATION]),
        ("What if I remove the car loan?", [DELETE_DATA, SIMULATION]),
        ("I earn 1.2 lakh a month", []),
        ],
    )
def test_match_rules(
    text: str,
    expected: list[str],
    ) -> None:

    """Each rule finds its keywords, and a message can hit several rules or none."""

    assert match_rules(text) == expected


@pytest.mark.parametrize(
    ("text", "simple"),
    [
        ("Delete my HDFC home loan", True),
        ("What if I spend ₹5,000 more each month?", True),
        ("Show my goals and what if I buy a car?", False),
        ("Don't delete the loan", False),
        ("Show my loans? Then my goals?", False),
        ("Please show me my goals from the last time we spoke about them in detail", False),
        ],
    )
def test_is_simple(
    text: str,
    simple: bool,
    ) -> None:

    """Joiners, negation, two questions or many words make a message not simple, but a comma inside an amount does not."""

    assert is_simple(text) is simple


async def test_one_simple_hit_skips_the_model(monkeypatch: pytest.MonkeyPatch) -> None:

    """A short message with one clear rule hit is answered by the rule, with no model call."""

    model = FakeIntentModel([ADD_DATA])

    use_model(monkeypatch, model)

    found, answer = await detect_current_intents([HumanMessage("Delete my HDFC home loan")])

    assert found == [DELETE_DATA]
    assert answer is None
    assert model.seen == []


async def test_mixed_message_goes_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:

    """A message that asks two things is sent to the model, and every intent it finds is kept in order."""

    use_model(monkeypatch, FakeIntentModel([VIEW_DATA, SIMULATION]))

    found, answer = await detect_current_intents([HumanMessage("Show my goals and what if I buy a car?")])

    assert found == [VIEW_DATA, SIMULATION]
    assert answer.usage_metadata == USAGE


async def test_model_answer_is_cleaned(monkeypatch: pytest.MonkeyPatch) -> None:

    """Repeats and unknown names are dropped, and an empty or unreadable answer becomes the fallback."""

    use_model(monkeypatch, FakeIntentModel([VIEW_DATA, "BANK_BALANCE", VIEW_DATA, GOAL_CHECK]))

    found, _ = await detect_current_intents([HumanMessage("yes")])

    assert found == [VIEW_DATA, GOAL_CHECK]

    use_model(monkeypatch, FakeIntentModel([]))

    assert (await detect_current_intents([HumanMessage("yes")]))[0] == FALLBACK_INTENTS

    use_model(monkeypatch, FakeIntentModel(None))

    assert (await detect_current_intents([HumanMessage("yes")]))[0] == FALLBACK_INTENTS


async def test_slow_model_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:

    """A model slower than the intent timeout is given up on, and the turn carries on with the fallback."""

    monkeypatch.setattr(get_settings(), "INTENT_TIMEOUT_SECONDS", 0.01)

    use_model(monkeypatch, FakeIntentModel([VIEW_DATA], delay=1))

    found, answer = await detect_current_intents([HumanMessage("yes")])

    assert found == FALLBACK_INTENTS
    assert answer is None


async def test_model_sees_only_the_last_few_chat_messages(monkeypatch: pytest.MonkeyPatch) -> None:

    """The model gets its instructions and the last four user and assistant messages, never tool results, and is never streamed."""

    model = FakeIntentModel([ADD_DATA])

    use_model(monkeypatch, model)

    history = [
        HumanMessage("I have a car loan"),
        AIMessage("", tool_calls=[{"name": "list_records", "args": {"kind": "loans"}, "id": "call-1"}]),
        ToolMessage("nothing saved", tool_call_id="call-1"),
        AIMessage("Is this a new loan?"),
        HumanMessage("It is from HDFC"),
        AIMessage("Is this a new one, or the one you told me about?"),
        HumanMessage("yes"),
        ]

    await detect_current_intents(history)

    assert [message.text for message in model.seen[1:]] == [
        "Is this a new loan?",
        "It is from HDFC",
        "Is this a new one, or the one you told me about?",
        "yes",
        ]
    assert model.tags == ["nostream"]


async def test_node_sets_intents_and_counts_only_tokens(monkeypatch: pytest.MonkeyPatch) -> None:

    """The node saves the intents and starts a fresh budget with the classifier's tokens but no model call."""

    use_model(monkeypatch, FakeIntentModel([VIEW_DATA, SIMULATION]))

    update = await classify_intents({"messages": [HumanMessage("Show my goals and what if I buy a car?")]})

    assert update["current_intents"] == [VIEW_DATA, SIMULATION]
    assert update["skip_reply"] is False
    assert update["budget"]["model_calls"] == 0
    assert (update["budget"]["input_tokens"], update["budget"]["output_tokens"]) == (120, 8)
