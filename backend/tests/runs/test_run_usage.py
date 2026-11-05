"""Tests that a finished run saves what its turn used, and the limit it reached, on the real database and checkpointer."""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessageChunk, ToolMessage

from app.agent import graph as planner
from app.agent.checkpointer import open_checkpointer
from app.core.config import get_settings
from app.db.enums import RunStatus
from app.db.models import AgentRun
from app.db.session import SessionLocal
from app.features.runs.worker import execute_run
from app.services import llm
from tests.support import SeededRun, create_user, delete_user_data, seed_run


TOKENS = {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200}


class Answerer:

    """A model that asks for get_missing_sections once, then answers in one line."""

    async def astream(self, messages: list) -> AsyncIterator[AIMessageChunk]:

        """Ask for the tool on the user's message, and answer after it ran."""

        if isinstance(messages[-1], ToolMessage):

            yield AIMessageChunk("Noted.", usage_metadata=TOKENS)

            return

        yield AIMessageChunk("", tool_call_chunks=[{"name": "get_missing_sections", "args": "{}", "id": "missing", "index": 0}])
        yield AIMessageChunk("", usage_metadata=TOKENS)


class Closer:

    """The wrap-up model, answering in one line."""

    async def astream(self, messages: list) -> AsyncIterator[AIMessageChunk]:

        """Close the turn."""

        yield AIMessageChunk("I checked what is missing. Ask me to carry on.", usage_metadata=TOKENS)


@pytest.fixture
async def seeded(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SeededRun]:

    """Give the test a queued run on the real checkpointer with the fake models, then delete the user and their thread."""

    monkeypatch.setattr(llm.llm_service, "with_tools", lambda tools, model=None, max_tokens=None: Answerer())
    monkeypatch.setattr(llm.llm_service, "without_acting", lambda tools, max_tokens, model=None: Closer())

    user_id = await create_user()

    async with open_checkpointer() as checkpointer:

        planner.planner_graph = planner.build_planner_graph(checkpointer)

        seeded_run = await seed_run(user_id)

        try:
            yield seeded_run

        finally:

            await checkpointer.adelete_thread(str(seeded_run.conversation_id))

            await delete_user_data(user_id)


async def run_once(seeded: SeededRun) -> AgentRun:

    """Run the seeded run to its end and return its saved row."""

    await execute_run(seeded.run_id, seeded.conversation_id, seeded.user_id, seeded.assistant_message_id, "hi")

    async with SessionLocal() as session:
        return await session.get(AgentRun, seeded.run_id)


async def test_completed_run_saves_its_usage_and_cost(
    seeded: SeededRun,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """Two model calls and one tool call are saved with their tokens and the cost at gpt-4o-mini's price."""

    monkeypatch.setattr(get_settings(), "CHAT_MODEL", "gpt-4o-mini")

    run = await run_once(seeded)

    assert run.status == RunStatus.completed
    assert (run.model_calls, run.tool_calls, run.input_tokens, run.output_tokens) == (2, 1, 2000, 400)
    assert run.cost_usd == Decimal("0.000540")
    assert run.failure_code is None


async def test_run_that_reached_a_limit_completes_and_says_which(
    seeded: SeededRun,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:

    """A turn stopped by the model call limit still completes, with its closing reply, and the limit is noted."""

    monkeypatch.setattr(get_settings(), "MAX_MODEL_CALLS", 1)

    run = await run_once(seeded)

    assert run.status == RunStatus.completed
    assert run.failure_code == "model_call_limit"
    assert run.model_calls == 2


async def test_unknown_model_saves_no_cost(seeded: SeededRun, monkeypatch: pytest.MonkeyPatch) -> None:

    """A model with no price set saves the usage but leaves the cost empty."""

    monkeypatch.setattr(get_settings(), "CHAT_MODEL", "some-other-model")

    run = await run_once(seeded)

    assert run.model_calls == 2
    assert run.cost_usd is None
