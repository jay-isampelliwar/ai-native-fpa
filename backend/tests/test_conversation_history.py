"""What the transcript tables must guarantee, which is mostly about order and ownership.

Every test here uses the repository directly rather than driving the graph. Whether a turn is
recorded is a property of the repository and the endpoint that calls it; whether the planner answers
correctly is tested elsewhere, and mixing the two would make a routing change break a history test
for no reason a reader could follow.

Ordering is asserted against ``position`` and not against timestamps on purpose. The bug this guards
is two rows written inside the same millisecond, which a timestamp comparison would pass on a slow
machine and fail on a fast one.

The ownership tests read with the wrong user id and expect nothing rather than an error, because that
is the contract every other surface in this service keeps: a record someone does not own is reported
exactly as one that does not exist.
"""

import pytest

pytestmark = pytest.mark.asyncio

CONVERSATION = "conv_history_test"

OTHER_USER = 9002


async def test_appending_creates_the_conversation_and_titles_it(api_user):

    """The first user message brings the session into existence and names it."""

    from app.repositories.conversations_repository import conversations_repository

    await conversations_repository.append(
        user_id=api_user,
        conversation_id=CONVERSATION,
        role="user",
        text="How much is left over this month?",
    )

    conversation = await conversations_repository.find(api_user, CONVERSATION)

    assert conversation is not None
    assert conversation.title == "How much is left over this month?"
    assert conversation.message_count == 1


async def test_turns_keep_the_order_they_were_written_in(api_user):

    """Positions increment per conversation, so a transcript never renders an answer above its question."""

    from app.repositories.conversations_repository import conversations_repository

    await conversations_repository.append(
        user_id=api_user,
        conversation_id=CONVERSATION,
        role="user",
        text="What is my surplus?",
    )

    await conversations_repository.append(
        user_id=api_user,
        conversation_id=CONVERSATION,
        role="planner",
        text="Your surplus is 24,000.",
        blocks=[{"type": "text", "text": "Your surplus is 24,000.", "evidence_ids": ["inc_1"]}],
        skill_name="cashflow_summary",
        status="answered",
        evidence_ids=["inc_1"],
        calculator_versions=["cashflow.v1"],
    )

    turns = await conversations_repository.transcript(api_user, CONVERSATION)

    assert [turn.position for turn in turns] == [1, 2]
    assert [turn.role for turn in turns] == ["user", "planner"]
    assert turns[1].calculator_versions == ["cashflow.v1"]


async def test_blocks_survive_the_round_trip(api_user):

    """A stored turn returns the blocks the client was shown rather than a re-rendered version."""

    from app.repositories.conversations_repository import conversations_repository

    blocks = [
        {
            "type": "kpi",
            "label": "Monthly surplus",
            "display": "₹24,000",
            "value": "24000.00",
            "caption": None,
            "tone": "positive",
            "evidence_ids": ["inc_1"],
        }
    ]

    await conversations_repository.append(
        user_id=api_user,
        conversation_id=CONVERSATION,
        role="planner",
        text="Your surplus is 24,000.",
        blocks=blocks,
    )

    turns = await conversations_repository.transcript(api_user, CONVERSATION)

    assert turns[0].blocks[0]["display"] == "₹24,000"
    assert turns[0].blocks[0]["value"] == "24000.00"


async def test_a_conversation_someone_does_not_own_reads_as_missing(api_user):

    """Ownership failures are reported as absence, exactly as they are on every other surface."""

    from app.repositories.conversations_repository import conversations_repository

    await conversations_repository.append(
        user_id=api_user,
        conversation_id=CONVERSATION,
        role="user",
        text="What is my surplus?",
    )

    assert await conversations_repository.find(OTHER_USER, CONVERSATION) is None
    assert await conversations_repository.transcript(OTHER_USER, CONVERSATION) == []


async def test_discarding_removes_the_conversation_and_its_turns(api_user):

    """Deleting a chat cascades to its messages and reports whether there was one to delete."""

    from app.repositories.conversations_repository import conversations_repository

    await conversations_repository.append(
        user_id=api_user,
        conversation_id=CONVERSATION,
        role="user",
        text="What is my surplus?",
    )

    assert await conversations_repository.discard(api_user, CONVERSATION) is True
    assert await conversations_repository.find(api_user, CONVERSATION) is None
    assert await conversations_repository.transcript(api_user, CONVERSATION) == []
    assert await conversations_repository.discard(api_user, CONVERSATION) is False


async def test_sessions_are_listed_most_recently_spoken_to_first(api_user):

    """The history panel's order is the repository's job, not the client's."""

    from app.repositories.conversations_repository import conversations_repository

    await conversations_repository.append(
        user_id=api_user,
        conversation_id="conv_history_older",
        role="user",
        text="An older question",
    )

    await conversations_repository.append(
        user_id=api_user,
        conversation_id="conv_history_newer",
        role="user",
        text="A newer question",
    )

    sessions = await conversations_repository.sessions(api_user)

    assert [session.id for session in sessions][:2] == ["conv_history_newer", "conv_history_older"]


async def test_the_endpoint_records_both_halves_of_a_turn(client, api_user):

    """Asking through the API leaves a question and an answer in the transcript, in that order."""

    from app.repositories.conversations_repository import conversations_repository

    response = client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "How much is left over this month?"},
    )

    assert response.status_code == 200

    conversation_id = response.json()["conversation_id"]

    listed = client.get(f"/api/v1/planner/conversations?user_id={api_user}")

    assert conversation_id in [session["id"] for session in listed.json()]

    detail = client.get(f"/api/v1/planner/conversations/{conversation_id}?user_id={api_user}")

    assert detail.status_code == 200

    roles = [message["role"] for message in detail.json()["messages"]]

    assert roles == ["user", "planner"]

    assert await conversations_repository.find(api_user, conversation_id) is not None


async def test_reading_someone_elses_conversation_is_a_404(client, api_user):

    """The API reports a conversation the caller does not own exactly as one that is not there."""

    response = client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "How much is left over this month?"},
    )

    conversation_id = response.json()["conversation_id"]

    denied = client.get(f"/api/v1/planner/conversations/{conversation_id}?user_id={OTHER_USER}")

    assert denied.status_code == 404


async def test_a_second_message_is_answered_rather_than_the_first_replayed(client, api_user):

    """State is checkpointed per thread, so a turn that inherits the last one answers a question nobody asked."""

    first = client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "How much is left over this month?"},
    ).json()

    second = client.post(
        "/api/v1/planner/messages",
        json={
            "user_id": api_user,
            "message": "How much is left over this month?",
            "conversation_id": first["conversation_id"],
        },
    ).json()

    assert second["conversation_id"] == first["conversation_id"]

    assert second["correlation_id"] != first["correlation_id"]


async def test_a_turn_inherits_nothing_from_the_one_before_it(api_user):

    """Every field a node fills is cleared, not only the response, so stale blocks cannot be rendered either."""

    from app.graphs.orchestrator.state import PlannerState, new_turn

    from app.ui.blocks import TextBlock

    stale = PlannerState(
        user_id=api_user,
        conversation_id="conv_stale",
        user_message="the first question",
        response="the first answer",
        tools_used=["cashflow_summary"],
        writes_performed=["added income Salary"],
        blocks=[TextBlock(text="last turn's table")],
        evidence_ids=["inc_1"],
        calculator_versions=["cashflow.v1"],
        assumptions={"months_per_year": 12.0},
    )

    fresh = PlannerState(**{**stale.model_dump(), **new_turn(api_user, "conv_stale", "the second question")})

    assert fresh.user_message == "the second question"
    assert fresh.response is None
    assert fresh.tools_used == []
    assert fresh.writes_performed == []
    assert fresh.blocks == []
    assert fresh.evidence_ids == []
    assert fresh.calculator_versions == []
    assert fresh.assumptions == {}


async def test_posting_to_someone_elses_conversation_is_a_404(client, api_user):

    """A conversation id is the graph's thread id, so accepting one from a stranger hands them the thread."""

    first = client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "How much is left over this month?"},
    ).json()

    intruded = client.post(
        "/api/v1/planner/messages",
        json={
            "user_id": OTHER_USER,
            "message": "hello",
            "conversation_id": first["conversation_id"],
        },
    )

    assert intruded.status_code == 404

    approved = client.post(
        "/api/v1/planner/approvals",
        json={
            "user_id": OTHER_USER,
            "conversation_id": first["conversation_id"],
            "decision": "approve",
        },
    )

    assert approved.status_code == 404


async def test_an_unknown_conversation_is_refused_rather_than_started(client, api_user):

    """A thread id nobody has is not a new conversation: accepting it would let a caller pick their own thread."""

    response = client.post(
        "/api/v1/planner/messages",
        json={"user_id": api_user, "message": "hello", "conversation_id": "conv_invented"},
    )

    assert response.status_code == 404


async def test_the_streaming_endpoint_records_both_halves_too(client, api_user):

    """The path the interface actually uses writes its answer from inside the generator."""

    from app.repositories.conversations_repository import conversations_repository

    with client.stream(
        "POST",
        "/api/v1/planner/messages/stream",
        json={"user_id": api_user, "message": "How much is left over this month?"},
    ) as response:

        assert response.status_code == 200

        body = "".join(response.iter_text())

    assert "event: done" in body

    sessions = await conversations_repository.sessions(api_user)

    assert sessions

    turns = await conversations_repository.transcript(api_user, sessions[0].id)

    assert [turn.role for turn in turns] == ["user", "planner"]
