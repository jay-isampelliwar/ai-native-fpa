"""Capturing a stated figure without letting the conversation write it, and what the panel then shows.

The rule these tests defend is the one the whole backend is shaped around: the conversation never
writes. Capture does not relax it, it relocates the check - the skill proposes, a card shows exactly
what would be stored, and the write happens only after someone approves. So the first thing asserted
is a negative: after the skill has run and before anyone has confirmed, the record tables are
untouched.

Extraction is stubbed throughout. What is under test is what happens to a candidate once it exists -
whether it is proposed, deduplicated, written on approval and refused without one - and none of that
is a property of the model. A test that needs an API key to prove an approval gate works is a test
that stops running the day the key expires.

The duplicate test matters more than it looks. Someone states their salary again in a later session
because the first exchange scrolled away, and a second income row does not fail loudly - it silently
doubles every surplus the planner will ever quote them.

The workspace tests assert absence as much as presence. A section that renders with dashes in it
teaches a person to ignore the panel, so a section with no data must not appear at all.
"""

import pytest

from app.graphs.skills.contracts import SkillContext, SkillRequest

pytestmark = pytest.mark.asyncio


def context_for(user_id: int) -> SkillContext:

    """Build the context the orchestrator would hand a skill for one request."""

    return SkillContext(user_id=user_id, conversation_id="conv_capture", correlation_id="req_capture")


def candidate(kind: str, label: str, amount: str, frequency: str = "monthly", remaining_months: int | None = None):

    """Build one extraction candidate, standing in for what the model would have returned."""

    from app.graphs.skills.record_capture.extraction import Candidate

    return Candidate(
        kind=kind,
        label=label,
        amount=amount,
        frequency=frequency,
        remaining_months=remaining_months,
    )


def stub_extraction(monkeypatch, candidates):

    """Replace the model call with a fixed list, so the approval gate is what is being tested."""

    from app.graphs.skills.record_capture import skill as skill_module

    async def fake(message: str):
        return candidates

    monkeypatch.setattr(skill_module, "extract_records", fake)


async def counts_for(user_id: int) -> dict:

    """Count what this user actually has in the record tables, which is the thing at stake."""

    from sqlalchemy import text

    from app.db.session import session_scope

    async with session_scope() as session:

        return {
            table: await session.scalar(text(f"SELECT count(*) FROM {table} WHERE user_id = :uid"), {"uid": user_id})
            for table in ("income_records", "expense_records", "emi_records", "sip_records", "liabilities")
        }


async def test_capture_proposes_and_writes_nothing_yet(api_user, monkeypatch):

    """The skill produces a proposal and leaves the record tables exactly as it found them."""

    from app.graphs.skills.record_capture.skill import RecordCaptureSkill

    stub_extraction(monkeypatch, [candidate("income", "Salary", "150000")])

    before = await counts_for(api_user)

    result = await RecordCaptureSkill().execute(SkillRequest(message="my salary is 1.5L"), context_for(api_user))

    assert result.status == "proposed"
    assert result.write_tool == "create_records"
    assert result.pending_approval_id is not None
    assert await counts_for(api_user) == before


async def test_the_card_shows_what_will_be_stored(api_user, monkeypatch):

    """The proposal names each record in the words the write will use, not a looser summary."""

    from app.graphs.skills.record_capture.skill import RecordCaptureSkill

    stub_extraction(
        monkeypatch,
        [candidate("income", "Salary", "150000"), candidate("emi", "Home loan", "42000", remaining_months=180)],
    )

    result = await RecordCaptureSkill().execute(SkillRequest(message="salary and emi"), context_for(api_user))

    labels = [change["label"] for change in result.proposed_changes]

    assert labels == ["Income · Salary", "Loan EMI · Home loan"]
    assert result.proposed_changes[0]["after"] == "₹150,000 a month"


async def test_approving_writes_every_confirmed_record(api_user, monkeypatch):

    """The controlled write applies the whole confirmed set, and an EMI brings its liability with it."""

    from app.approvals.store import approval_store
    from app.core.security import local_user
    from app.graphs.skills.record_capture.skill import RecordCaptureSkill
    from app.tools.controlled_write.writes import create_records

    stub_extraction(
        monkeypatch,
        [
            candidate("income", "Salary", "150000"),
            candidate("expense", "Rent", "30000"),
            candidate("emi", "Home loan", "42000", remaining_months=180),
        ],
    )

    result = await RecordCaptureSkill().execute(SkillRequest(message="all three"), context_for(api_user))

    approval = await approval_store.decide(result.pending_approval_id, api_user, "approve")

    outcome = await create_records(local_user(api_user), approval)

    assert outcome.status == "completed"

    counts = await counts_for(api_user)

    assert counts["income_records"] == 1
    assert counts["expense_records"] == 1
    assert counts["emi_records"] == 1
    assert counts["liabilities"] == 1


async def test_an_unapproved_proposal_writes_nothing(api_user, monkeypatch):

    """The write refuses a proposal nobody confirmed, which is the guarantee the card exists for."""

    from app.approvals.store import approval_store
    from app.core.security import local_user
    from app.graphs.skills.record_capture.skill import RecordCaptureSkill
    from app.tools.controlled_write.writes import create_records

    stub_extraction(monkeypatch, [candidate("income", "Salary", "150000")])

    result = await RecordCaptureSkill().execute(SkillRequest(message="my salary"), context_for(api_user))

    approval = await approval_store.get(result.pending_approval_id, api_user)

    outcome = await create_records(local_user(api_user), approval)

    assert outcome.status == "refused"
    assert (await counts_for(api_user))["income_records"] == 0


async def test_a_record_already_held_is_not_proposed_again(api_user, monkeypatch):

    """Stating the same thing twice is refused, because a second income row doubles every surplus."""

    from app.approvals.store import approval_store
    from app.core.security import local_user
    from app.graphs.skills.record_capture.skill import RecordCaptureSkill
    from app.tools.controlled_write.writes import create_records

    stub_extraction(monkeypatch, [candidate("income", "Salary", "150000")])

    first = await RecordCaptureSkill().execute(SkillRequest(message="my salary"), context_for(api_user))

    approval = await approval_store.decide(first.pending_approval_id, api_user, "approve")

    await create_records(local_user(api_user), approval)

    second = await RecordCaptureSkill().execute(SkillRequest(message="my salary is 1.5L"), context_for(api_user))

    assert second.status == "refused"
    assert "already have" in second.message.lower()
    assert (await counts_for(api_user))["income_records"] == 1


async def test_nothing_stated_is_refused_rather_than_invented(api_user, monkeypatch):

    """A sentence with no figure in it produces a refusal, never an empty or guessed record."""

    from app.graphs.skills.record_capture.skill import RecordCaptureSkill

    stub_extraction(monkeypatch, [])

    result = await RecordCaptureSkill().execute(SkillRequest(message="hello there"), context_for(api_user))

    assert result.status == "refused"
    assert result.pending_approval_id is None


async def test_the_workspace_reports_what_is_missing_before_anything_exists(api_user):

    """A person who has given nothing gets a checklist, which is the panel's job before it has data."""

    from app.services.workspace import build_workspace

    readiness, sections = await build_workspace(api_user)

    assert readiness["has_any_records"] is False
    assert readiness["can_compute_cashflow"] is False
    assert set(readiness["missing"]) == {"income", "expenses", "emis", "sips"}
    assert [section.key for section in sections] == []


async def test_the_cashflow_section_appears_once_it_can_be_computed(api_user, monkeypatch):

    """The panel gains a section the moment there is data for it, and not before."""

    from app.approvals.store import approval_store
    from app.core.security import local_user
    from app.graphs.skills.record_capture.skill import RecordCaptureSkill
    from app.services.workspace import build_workspace
    from app.tools.controlled_write.writes import create_records

    stub_extraction(
        monkeypatch,
        [candidate("income", "Salary", "150000"), candidate("expense", "Rent", "30000")],
    )

    result = await RecordCaptureSkill().execute(SkillRequest(message="salary and rent"), context_for(api_user))

    approval = await approval_store.decide(result.pending_approval_id, api_user, "approve")

    await create_records(local_user(api_user), approval)

    readiness, sections = await build_workspace(api_user)

    assert readiness["can_compute_cashflow"] is True

    assert "cashflow" in [section.key for section in sections]

    blocks = next(section for section in sections if section.key == "cashflow").blocks

    assert [block.type for block in blocks][:1] == ["kpi"]


async def test_the_workspace_endpoint_returns_the_same_shape(client, api_user):

    """The panel's one read is reachable and narrows to the schema the client renders."""

    response = client.get(f"/api/v1/workspace?user_id={api_user}")

    assert response.status_code == 200

    body = response.json()

    assert body["user_id"] == api_user
    assert body["readiness"]["has_any_records"] is False
    assert isinstance(body["sections"], list)


async def test_an_emi_without_a_tenure_is_asked_about_not_invented(api_user, monkeypatch):

    """A loan with no stated term is a question, because the database and every projection need one."""

    from app.graphs.skills.record_capture.skill import RecordCaptureSkill

    stub_extraction(monkeypatch, [candidate("emi", "Home loan", "42000")])

    result = await RecordCaptureSkill().execute(SkillRequest(message="I pay 42k on my home loan"), context_for(api_user))

    assert result.status == "refused"
    assert "how many months are left" in result.message
    assert (await counts_for(api_user))["liabilities"] == 0


async def test_the_rest_of_a_message_is_still_proposed(api_user, monkeypatch):

    """Volunteering more should not cost someone the part that was complete."""

    from app.graphs.skills.record_capture.skill import RecordCaptureSkill

    stub_extraction(
        monkeypatch,
        [candidate("income", "Salary", "150000"), candidate("emi", "Home loan", "42000")],
    )

    result = await RecordCaptureSkill().execute(SkillRequest(message="salary and a loan"), context_for(api_user))

    assert result.status == "proposed"
    assert [change["label"] for change in result.proposed_changes] == ["Income · Salary"]
    assert "how many months are left" in result.message


async def test_no_savings_alert_is_raised_for_someone_with_no_income(api_user):

    """Telling a person who has given nothing that they save nothing is arithmetic, not a finding."""

    from app.alerts.service import alert_service

    kinds = [alert.kind for alert in await alert_service.evaluate(api_user)]

    assert "low_savings_rate" not in kinds
