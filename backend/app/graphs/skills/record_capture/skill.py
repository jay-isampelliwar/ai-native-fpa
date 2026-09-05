"""Proposing records from what a person said, so the conversation can capture data without writing it.

The rule this backend enforces is that the conversation never writes. This skill is what lets a
person answer "what do you need from me?" in their own words without breaking that rule: it reads the
sentence, builds candidate records, stores them as a pending approval, and stops. The card the person
sees is the check that used to be a form, and the orchestrator performs the write only after they
press Add. Nothing here can reach a record table, and the validator would reject this skill if it
claimed it had.

Duplicates are refused rather than proposed. Someone who states their salary twice - in two sessions,
or because the first attempt scrolled away - should be told it is already recorded, because a second
income row silently doubles every surplus figure the planner will ever quote them. The check is by
label and kind, which is what a person would recognise as "the same thing", not by amount: a salary
that changed is a correction to make deliberately, not a second job.

All the candidates from one message go into one approval. Someone answering the interview says three
things in a sentence, and being asked to confirm each of them separately is a worse experience than
being shown all three at once. The write applies them in one transaction for the same reason.

``proposed_changes`` is built here rather than in the interface, so the card shows exactly the fields
that will be stored. A card that summarises a proposal in different words than the write uses is a
card that can be honestly agreed to and still surprise someone.

An EMI with no stated tenure is asked about rather than proposed. The database refuses a liability
without a term and it is right to: a debt with no end date breaks every projection that later tries
to use it. "I pay 42k on my home loan" has not said how long is left, so the answer is a question,
not a plausible number nobody chose. Everything else in the same message is still proposed, because
holding back a salary until a loan question is answered would punish the person for volunteering
more.

The result carries no evidence identifiers, and the definition sets ``quotes_figures`` False so the
validator permits that. Nothing here concludes anything about existing records; it reports what the
person just said back to them.
"""

from decimal import Decimal

from app.approvals.store import approval_store
from app.db.session import session_scope
from app.graphs.skills.contracts import SkillContext, SkillRequest, SkillResult
from app.graphs.skills.record_capture.definition import DEFINITION
from app.graphs.skills.record_capture.extraction import Candidate, extract_records, to_amount
from app.repositories import get_cashflow_repository
from app.repositories.cashflow_repository import CashflowRepository
from app.ui.blocks import CalloutBlock

FREQUENCY_WORDS = {
    "monthly": "a month",
    "quarterly": "a quarter",
    "half_yearly": "every six months",
    "annual": "a year",
    "one_off": "once",
}

KIND_WORDS = {
    "income": "Income",
    "expense": "Expense",
    "emi": "Loan EMI",
    "sip": "SIP",
}


class RecordCaptureSkill:

    """Reads financial facts out of a sentence and proposes them as records for a person to confirm."""

    name = DEFINITION.name
    version = DEFINITION.version

    def __init__(self, repository: CashflowRepository | None = None) -> None:

        """Take the repository used to spot records the person has already given."""

        self._repository = repository or get_cashflow_repository()

    async def execute(
        self,
        request: SkillRequest,
        context: SkillContext,
        ) -> SkillResult:

        """Extract what was stated, drop what is already recorded, and propose the rest for approval."""

        candidates = await extract_records(request.message)

        if not candidates:
            return SkillResult(
                status="refused",
                message=(
                    "I could not find a figure to record in that. Tell me an amount and what it is "
                    "for - \"my salary is 1.5L a month\" - and I will add it."
                ),
            )

        existing = await self.existing_labels(context.user_id)

        known = [candidate for candidate in candidates if key(candidate) not in existing]

        duplicates = [candidate for candidate in candidates if key(candidate) in existing]

        incomplete = [candidate for candidate in known if not complete(candidate)]

        fresh = [candidate for candidate in known if complete(candidate)]

        if not fresh and incomplete:
            return SkillResult(
                status="refused",
                message=self.needs_more(incomplete),
            )

        if not fresh:
            return SkillResult(
                status="refused",
                message=self.already_have(duplicates),
                blocks=[CalloutBlock(level="note", text=self.already_have(duplicates))],
            )

        records = [to_record(candidate) for candidate in fresh]

        async with session_scope() as session:

            approval = await approval_store.create(
                session,
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                correlation_id=context.correlation_id,
                skill_name=DEFINITION.name,
                skill_version=DEFINITION.version,
                action_kind="create_records",
                after_state={"records": records},
                target_table="records",
            )

            approval_id = approval.id

        return SkillResult(
            status="proposed",
            message=self.summarise(fresh, duplicates, incomplete),
            pending_approval_id=approval_id,
            write_tool="create_records",
            proposed_changes=[
                {
                    "label": f"{KIND_WORDS[candidate.kind]} · {candidate.label}",
                    "before": None,
                    "after": describe(candidate),
                }
                for candidate in fresh
            ],
        )

    async def existing_labels(self, user_id: int) -> set[tuple[str, str]]:

        """Build the set of records this person already has, so nothing is proposed twice."""

        records = await self._repository.get_cashflow_records(user_id)

        held = set()

        for record in records.income:
            held.add(("income", record.label.strip().lower()))

        for record in records.expenses:
            held.add(("expense", record.label.strip().lower()))

        for record in records.emis:
            held.add(("emi", record.label.strip().lower()))

        for record in records.sips:
            held.add(("sip", record.scheme_name.strip().lower()))

        return held

    def summarise(
        self,
        fresh: list[Candidate],
        duplicates: list[Candidate],
        incomplete: list[Candidate],
        ) -> str:

        """Say what is about to be stored, and what was left out for being known or unfinished."""

        listed = ", ".join(f"{candidate.label} at {describe(candidate)}" for candidate in fresh)

        parts = [f"I read that as {listed}. Add it to your records?"]

        if duplicates:
            parts.append(self.already_have(duplicates))

        if incomplete:
            parts.append(self.needs_more(incomplete))

        return " ".join(parts)

    def needs_more(self, incomplete: list[Candidate]) -> str:

        """Ask for the one thing an EMI cannot be stored without, rather than inventing it."""

        listed = ", ".join(candidate.label for candidate in incomplete)

        return (
            f"For {listed} I also need how many months are left on it - a loan with no end date "
            "would break every projection that used it."
        )

    def already_have(self, duplicates: list[Candidate]) -> str:

        """Name the records that were skipped, since silently dropping them looks like being ignored."""

        listed = ", ".join(candidate.label for candidate in duplicates)

        return f"I already have {listed} on record, so I have not added it again."


def complete(candidate: Candidate) -> bool:

    """Report whether a candidate holds everything its record type cannot be stored without."""

    if candidate.kind != "emi":
        return True

    return bool(candidate.remaining_months)


def key(candidate: Candidate) -> tuple[str, str]:

    """Identify a record the way a person would - by what it is and what they call it."""

    return (candidate.kind, candidate.label.strip().lower())


def describe(candidate: Candidate) -> str:

    """Render one candidate as the phrase the confirmation card shows."""

    amount = to_amount(candidate.amount) or Decimal("0")

    return f"₹{amount:,.0f} {FREQUENCY_WORDS[candidate.frequency]}"


def to_record(candidate: Candidate) -> dict:

    """Shape one candidate into the payload the controlled write knows how to store."""

    fields = {
        "label": candidate.label,
        "amount": str(to_amount(candidate.amount)),
        "frequency": candidate.frequency,
    }

    if candidate.kind == "expense":
        fields["category"] = candidate.category or "general"

    if candidate.kind == "income":
        fields["source"] = candidate.category or "salary"

    if candidate.kind == "emi":
        fields["lender"] = candidate.lender or ""
        fields["remaining_months"] = candidate.remaining_months
        fields["interest_rate_percent"] = str(candidate.interest_rate_percent or 0)

    return {"kind": candidate.kind, "fields": fields}
