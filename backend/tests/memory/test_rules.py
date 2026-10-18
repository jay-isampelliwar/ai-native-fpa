"""Tests for the memory rules and the extractor, with a fake LLM reply and no real OpenAI call."""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.enums import MemoryStatus, MessageRole
from app.features.memory import extractor
from app.features.memory.rules import apply_rules, decide_status, is_blocked_key
from app.features.memory.schemas import ExtractedMemory, ExtractionResult


USER_MESSAGE_ID = 101

ASSISTANT_MESSAGE_ID = 102


def proposed(**overrides: Any) -> ExtractedMemory:

    """A valid explicit tobacco preference, with any field replaced."""

    values = {
        "memory_type": "preference",
        "namespace": "investment_preferences",
        "memory_key": "excluded_sectors",
        "content": {"sectors": ["tobacco"], "stance": "avoid"},
        "source_message_id": USER_MESSAGE_ID,
        "confidence": 0.9,
        "explicit": True,
        }

    return ExtractedMemory(**{**values, **overrides})


def kept(*memories: ExtractedMemory) -> list:

    """Run the rules with the one user message id this run has."""

    return apply_rules(list(memories), {USER_MESSAGE_ID})


@pytest.mark.parametrize(
    ("confidence", "explicit", "expected"),
    [
        (Decimal("0.9"), True, MemoryStatus.active),
        (Decimal("0.8"), True, MemoryStatus.active),
        (Decimal("0.9"), False, MemoryStatus.candidate),
        (Decimal("0.6"), True, MemoryStatus.candidate),
        (Decimal("0.5"), False, MemoryStatus.candidate),
        (Decimal("0.49"), True, None),
        ],
    )
def test_decide_status(
    confidence: Decimal,
    explicit: bool,
    expected: MemoryStatus | None,
    ) -> None:

    """Explicit and sure is active, inferred or less sure is candidate, under 0.5 is dropped."""

    assert decide_status(confidence, explicit) == expected


def test_valid_preference_is_kept_active() -> None:

    """A valid explicit preference passes with its confidence and source."""

    [candidate] = kept(proposed())

    assert candidate.status == MemoryStatus.active
    assert candidate.confidence == Decimal("0.9")
    assert candidate.source_message_id == USER_MESSAGE_ID


@pytest.mark.parametrize(
    "override",
    [
        {"memory_type": "fact"},
        {"namespace": "random_stuff"},
        {"memory_key": "risk_appetite"},
        {"memory_key": "monthly_income"},
        {"memory_key": "bank_balance"},
        {"content": {}},
        {"content": {"sectors": ["tobacco"]}},
        {"content": {"sectors": ["tobacco"], "stance": "maybe"}},
        {"source_message_id": ASSISTANT_MESSAGE_ID},
        {"confidence": 0.3},
        ],
    )
def test_rule_breaking_memory_is_dropped(override: dict[str, Any]) -> None:

    """A wrong type, namespace, blocked key, empty content, missing stance, non-user source or low confidence drops the memory."""

    assert kept(proposed(**override)) == []


def test_stance_only_needed_for_investment_preferences() -> None:

    """An episodic memory needs no stance, while an investment preference must say avoid or prefer."""

    [candidate] = kept(proposed(memory_type="episodic", namespace="life_events", memory_key="daughter_college", content={"year": 2030}))

    assert candidate.namespace == "life_events"


def test_blocked_key_matches_parts() -> None:

    """Keys that only contain a blocked word are still blocked, and normal keys are not."""

    assert is_blocked_key("Preferred_Currency")
    assert not is_blocked_key("excluded_sectors")


def test_same_key_keeps_most_confident() -> None:

    """Two proposals for one key in a run keep only the more confident one."""

    [candidate] = kept(
        proposed(content={"sectors": ["tobacco"], "stance": "avoid"}, confidence=0.7),
        proposed(content={"sectors": ["tobacco", "gambling"], "stance": "avoid"}, confidence=0.95),
        )

    assert candidate.content == {"sectors": ["tobacco", "gambling"], "stance": "avoid"}


def test_confidence_is_clamped() -> None:

    """A confidence above 1 is stored as 1."""

    [candidate] = kept(proposed(confidence=1.7))

    assert candidate.confidence == Decimal("1.0")


class FakeModel:

    """Stands in for the chat model, returning a fixed structured reply and recording the prompt."""

    def __init__(self, result: ExtractionResult) -> None:

        """Keep the reply to return."""

        self.result = result
        self.prompt: list | None = None

    def with_structured_output(self, schema: type, method: str) -> "FakeModel":

        """Return itself, as the real model returns a structured runnable."""

        return self

    async def ainvoke(self, prompt: list) -> ExtractionResult:

        """Record the prompt and return the fixed reply."""

        self.prompt = prompt

        return self.result


def message(
    message_id: int,
    role: MessageRole,
    text: str,
    ) -> SimpleNamespace:

    """A stand-in message row with an id, role and text content."""

    return SimpleNamespace(id=message_id, role=role, content={"text": text})


async def test_extractor_applies_rules_to_llm_reply(monkeypatch: pytest.MonkeyPatch) -> None:

    """The extractor sends the chat with ids and existing memories, and keeps only the replies that pass the rules."""

    fake = FakeModel(ExtractionResult(memories=[proposed(), proposed(memory_key="risk_appetite")]))

    monkeypatch.setattr(extractor.llm_service, "get_model", lambda name: fake)

    messages = [
        message(USER_MESSAGE_ID, MessageRole.user, "I avoid tobacco stocks"),
        message(ASSISTANT_MESSAGE_ID, MessageRole.assistant, "Noted, I will leave out tobacco."),
        ]

    existing = [SimpleNamespace(namespace="investment_preferences", memory_key="excluded_sectors", content={"sectors": []})]

    candidates = await extractor.extract_candidates(messages, existing)

    assert [candidate.memory_key for candidate in candidates] == ["excluded_sectors"]

    body = fake.prompt[1].content

    assert "[message 101] user: I avoid tobacco stocks" in body
    assert '"memory_key":"excluded_sectors"' in body


async def test_extractor_skips_runs_without_user_message(monkeypatch: pytest.MonkeyPatch) -> None:

    """A run with no user message never calls the LLM."""

    monkeypatch.setattr(extractor.llm_service, "get_model", lambda name: pytest.fail("LLM was called"))

    assert await extractor.extract_candidates([], []) == []
