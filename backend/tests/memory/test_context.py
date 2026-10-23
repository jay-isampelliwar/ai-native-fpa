"""Tests for turning saved memories into prompt lines, and for the load_memories graph node on the real database."""

from types import SimpleNamespace
from typing import Any

from app.agent.budget import new_budget
from app.agent.context import PlannerContext
from app.agent.nodes import MEMORY_LIMIT, load_memories, run_agent
from app.db.enums import MemoryStatus
from app.db.models import MemoryItem
from app.db.session import SessionLocal
from app.features.memory.context import describe_memories, describe_memory
from tests.support import SeededRun, create_user, delete_user_data


def memory(
    namespace: str,
    memory_key: str | None,
    content: dict[str, Any],
    ) -> SimpleNamespace:

    """A stand-in memory row with only the fields the formatter reads."""

    return SimpleNamespace(namespace=namespace, memory_key=memory_key, content=content)


def test_avoid_preference_reads_as_avoids() -> None:

    """An avoid stance becomes the verb, so a dislike can never read as a liking."""

    line = describe_memory(memory("investment_preferences", "excluded_sectors", {"sectors": ["tobacco", "alcohol"], "stance": "avoid"}))

    assert line == "Investment: avoids sectors: tobacco, alcohol"


def test_prefer_preference_reads_as_prefers() -> None:

    """A prefer stance becomes the verb."""

    line = describe_memory(memory("investment_preferences", "preferred_sectors", {"sectors": ["pharma", "IT"], "stance": "prefer"}))

    assert line == "Investment: prefers sectors: pharma, IT"


def test_episodic_memory_names_its_key() -> None:

    """A memory with no stance shows its key in words, then its details."""

    line = describe_memory(memory("life_events", "daughter_starts_college", {"year": 2030}))

    assert line == "Life event: daughter starts college - year: 2030"


def test_unknown_namespace_and_nested_content() -> None:

    """An unknown namespace is turned into words, and nested content is flattened."""

    line = describe_memory(memory("other_things", "home_city", {"place": {"city": "Pune"}}))

    assert line == "Other things: home city - place: city: Pune"


def test_memory_block_lists_lines_or_says_nothing() -> None:

    """The memory message has its heading, then each line, or says nothing is remembered yet."""

    assert describe_memories([]) == "## What you remember about the user\nNothing yet."
    assert describe_memories(["Investment: avoids sectors: tobacco"]) == (
        "## What you remember about the user\n"
        "These come from the user's past chats.\n"
        "- Investment: avoids sectors: tobacco"
        )


async def add_memories(
    user_id: int,
    rows: list[tuple[str, dict[str, Any], MemoryStatus]],
    ) -> None:

    """Insert memory rows for one user directly."""

    async with SessionLocal() as session:

        for key, content, status in rows:

            session.add(
                MemoryItem(
                    user_id=user_id,
                    memory_type="preference",
                    namespace="investment_preferences",
                    memory_key=key,
                    content=content,
                    status=status,
                    )
                )

        await session.commit()


def runtime_for(user_id: int) -> SimpleNamespace:

    """A stand-in graph runtime carrying only the user's context."""

    return SimpleNamespace(context=PlannerContext(user_id=user_id))


async def test_load_memories_reads_only_own_active_memories(seeded_run: SeededRun) -> None:

    """The node returns the user's active memories as lines, skipping candidates and other users' rows."""

    other_user_id = await create_user()

    try:

        await add_memories(seeded_run.user_id, [
            ("excluded_sectors", {"sectors": ["tobacco"], "stance": "avoid"}, MemoryStatus.active),
            ("preferred_sectors", {"sectors": ["pharma"], "stance": "prefer"}, MemoryStatus.candidate),
            ])
        await add_memories(other_user_id, [
            ("excluded_sectors", {"sectors": ["alcohol"], "stance": "avoid"}, MemoryStatus.active),
            ])

        update = await load_memories({"messages": []}, runtime_for(seeded_run.user_id))

        assert update == {"memories": ["Investment: avoids sectors: tobacco"], "skip_reply": False, "budget": new_budget()}

    finally:
        await delete_user_data(other_user_id)


async def test_load_memories_caps_at_limit_newest_first(seeded_run: SeededRun) -> None:

    """More than the limit of active memories loads only the newest ones."""

    rows = [(f"rule_{index}", {"sectors": [f"s{index}"], "stance": "avoid"}, MemoryStatus.active) for index in range(MEMORY_LIMIT + 5)]

    await add_memories(seeded_run.user_id, rows)

    update = await load_memories({"messages": []}, runtime_for(seeded_run.user_id))

    assert len(update["memories"]) == MEMORY_LIMIT
    assert update["memories"][0] == f"Investment: avoids sectors: s{MEMORY_LIMIT + 4}"


async def test_agent_prompt_includes_memories(monkeypatch) -> None:

    """run_agent sends the base prompt and the memories as two separate system messages, before the chat."""

    sent: list = []

    class FakeModel:

        """Records the messages and streams nothing back."""

        async def astream(self, messages: list):

            """Keep the messages and yield no chunks."""

            sent.extend(messages)

            return

            yield

    monkeypatch.setattr("app.agent.nodes.llm_service.with_tools", lambda tools, max_tokens=None: FakeModel())

    state = {"messages": [], "memories": ["Investment: avoids sectors: tobacco"]}

    await run_agent(state, runtime_for(1))

    assert [message.type for message in sent] == ["system", "system"]
    assert "Investment" not in sent[0].content
    assert sent[1].content.startswith("## What you remember about the user")
    assert "- Investment: avoids sectors: tobacco" in sent[1].content
