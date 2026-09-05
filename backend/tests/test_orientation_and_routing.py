"""What happens to a request no financial skill fits, which used to be a refusal about cash flow.

Two failures are covered here and they compound. The router was told to pick the closest skill when
nothing fit, so a greeting became a cash flow request; nothing then acted on the confidence it
returned, so a 0.3 match executed exactly as a 0.95 match would. A person's first two messages both
came back as the same refusal about records they had never been asked for.

The routing tests stub the model rather than calling it. What is under test is the decision made
about a confidence, not the confidence itself - and a test that needs an API key to prove a threshold
works is a test nobody runs.

The orientation tests use the in memory repository so they can assert both halves: what the skill
says to someone with no records at all, and what it says to someone missing only some. The second
case is the one worth having, because telling a person to send records they have already sent is the
failure that makes an assistant feel like it is not listening.
"""

import pytest

from app.graphs.skills.contracts import SkillContext, SkillRequest

pytestmark = pytest.mark.asyncio

CONTEXT = SkillContext(user_id=1, conversation_id="conv_orientation", correlation_id="req_orientation")


class EmptyRepository:

    """A repository for someone who has given the planner nothing yet."""

    async def get_cashflow_records(self, user_id: int):

        """Return an empty bundle, the state every new user starts in."""

        from app.models.finance import CashflowRecords

        return CashflowRecords(income=[], expenses=[], emis=[], sips=[])


async def test_a_new_user_is_told_what_to_send_rather_than_refused():

    """Someone with no records gets an orientation, not a refusal about cash flow."""

    from app.graphs.skills.orientation.skill import OrientationSkill

    result = await OrientationSkill(EmptyRepository()).execute(SkillRequest(message="Hey, how can you help me?"), CONTEXT)

    assert result.status == "answered"
    assert "attach a statement" in result.message.lower()


async def test_the_capability_list_comes_from_the_registry():

    """What the planner says it can do is read from what is registered, so it cannot go stale."""

    from app.graphs.skills.bootstrap import register_skills
    from app.graphs.skills.orientation.skill import OrientationSkill

    register_skills()

    result = await OrientationSkill(EmptyRepository()).execute(SkillRequest(message="what can you do"), CONTEXT)

    text = result.blocks[0].text

    assert "Summarise this month's income" in text
    assert "orientation" not in text.lower()


async def test_it_asks_only_for_the_records_that_are_missing(seeded_records):

    """Someone who has already sent their records is not asked to send them again."""

    from app.graphs.skills.orientation.skill import OrientationSkill
    from app.repositories import get_cashflow_repository

    result = await OrientationSkill(get_cashflow_repository()).execute(SkillRequest(message="what do you need"), CONTEXT)

    assert "I have everything I need" in result.message

    assert not [block for block in result.blocks if block.type == "callout"]


async def test_an_orientation_answer_passes_validation_without_evidence():

    """The evidence rule is waived only for a skill that quotes no figure, and this is that skill."""

    from app.graphs.orchestrator.nodes import validate_skill_result
    from app.graphs.orchestrator.state import PlannerState
    from app.graphs.skills.orientation.definition import DEFINITION
    from app.graphs.skills.orientation.skill import OrientationSkill

    result = await OrientationSkill(EmptyRepository()).execute(SkillRequest(message="hello"), CONTEXT)

    state = PlannerState(
        user_id=1,
        conversation_id="conv_orientation",
        user_message="hello",
        definition=DEFINITION,
        result=result,
    )

    assert validate_skill_result(state)["validation_errors"] == []


async def test_a_skill_that_quotes_figures_still_needs_evidence():

    """Waiving the rule for orientation must not weaken it for anything that reports a number."""

    from app.graphs.orchestrator.nodes import validate_skill_result
    from app.graphs.orchestrator.state import PlannerState
    from app.graphs.skills.cashflow_summary.definition import DEFINITION
    from app.graphs.skills.contracts import SkillResult

    state = PlannerState(
        user_id=1,
        conversation_id="conv_orientation",
        user_message="what is my surplus",
        definition=DEFINITION,
        result=SkillResult(status="answered", message="Your surplus is 61,000."),
    )

    errors = validate_skill_result(state)["validation_errors"]

    assert "a material conclusion was returned without evidence identifiers" in errors


async def test_a_low_confidence_route_is_answered_with_orientation(monkeypatch):

    """A router that is unsure hands over instead of running the closest skill anyway."""

    from app.graphs.orchestrator import router as router_module
    from app.graphs.skills.bootstrap import register_skills

    register_skills()

    decision = router_module.RouteDecision(
        skill="cashflow_summary",
        confidence=0.3,
        reason="The request implies a need for financial data.",
    )

    monkeypatch.setattr(router_module, "get_router_model", lambda: StubModel(decision))

    state = router_module.PlannerState(user_id=1, conversation_id="conv_orientation", user_message="Hey, how can you help me?")

    outcome = await router_module.route_request(state)

    assert outcome["skill_name"] == "orientation"
    assert outcome["route_confidence"] == 0.3
    assert "below the floor" in outcome["route_reason"]


async def test_a_confident_route_is_left_alone(monkeypatch):

    """The floor must not intercept a request the router actually understood."""

    from app.graphs.orchestrator import router as router_module
    from app.graphs.skills.bootstrap import register_skills

    register_skills()

    decision = router_module.RouteDecision(
        skill="cashflow_summary",
        confidence=0.95,
        reason="A direct question about this month's surplus.",
    )

    monkeypatch.setattr(router_module, "get_router_model", lambda: StubModel(decision))

    state = router_module.PlannerState(user_id=1, conversation_id="conv_orientation", user_message="what is my surplus")

    outcome = await router_module.route_request(state)

    assert outcome["skill_name"] == "cashflow_summary"


class StubModel:

    """Stands in for the router model so a threshold can be tested without an API key."""

    def __init__(self, decision) -> None:

        """Keep the decision every structured call should return."""

        self._decision = decision

    def with_structured_output(self, schema):

        """Ignore the schema and return self, matching the one call the router makes."""

        return self

    async def ainvoke(self, messages):

        """Return the prepared decision regardless of what was asked."""

        return self._decision
