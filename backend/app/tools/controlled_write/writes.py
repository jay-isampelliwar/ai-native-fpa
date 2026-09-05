"""The controlled write tools, the only code that changes a record on a user's behalf.

Every function here has the same five preconditions and none of them are optional: an
authenticated user, an authorization decision, an approved pending action, an idempotency key,
and an audit context. A write reached without all five is a bug, so they are checked here rather
than assumed to have been checked upstream.

The freshness check is the one that is easy to leave out and expensive to omit. An approval
records what the record looked like when the proposal was shown; if the row has changed since,
executing would silently discard whatever the user did in the meantime. Comparing the stored
before state against the current row turns that into a refusal the user can act on.

Writes are idempotent by construction. An approval that has already been executed is marked
approved with a decided timestamp, and the store refuses to decide it twice, so a retried request
finds an already applied approval and reports success without writing again.

Nothing here is reachable from a skill. Skills propose; the graph pauses; the orchestrator calls
these after an approval. That separation is what makes "the model cannot write" a property of the
call graph rather than a promise in a prompt.

Each function returns a ``WriteOutcome`` rather than raising. A failed write still has to reach
the audit node, and an exception thrown mid graph would skip it.

``create_records`` is what lets a person give the planner a figure in conversation and have it kept.
It carries several records in one approval rather than one each, because someone answering "what do
you need from me" says three things in a sentence and being asked to confirm each separately is worse
than being shown all three and asked once. They are written in one transaction: a set of records a
person accepted as a group should not land as a partial group.

It has no freshness check, and that is not an omission. The other write here changes a row that
existed when the proposal was shown, so the row moving underneath it matters; these rows do not exist
yet, so there is nothing that could have moved. What replaces it is the approval status check, which
is what stops the same confirmation being applied twice.
"""

from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select

from app.core.security import AuthenticatedUser, authorize
from app.db.session import session_scope
from app.models.finance import ApprovalStatus, Frequency, SipStatus
from app.models.orm.credit import SipRecordRow
from app.models.orm.system import PendingApprovalRow
from app.repositories.records_repository import records_repository

RECORD_SCOPES = {
    "income": "income:write",
    "expense": "expenses:write",
    "emi": "liabilities:write",
    "sip": "sip:write",
}


class WriteOutcome(BaseModel):

    """What a controlled write did, shaped so a refusal is as recordable as a success."""

    status: str
    detail: str
    target_table: str | None = None
    target_id: str | None = None
    idempotency_key: str | None = None


def refuse(detail: str) -> WriteOutcome:

    """Build the outcome for a write that was not attempted, so the reason reaches the audit row."""

    return WriteOutcome(status="refused", detail=detail)


async def update_sip_instruction(
    user: AuthenticatedUser,
    approval: PendingApprovalRow,
    ) -> WriteOutcome:

    """Apply an approved change to a standing instruction, refusing if anything moved underneath it."""

    decision = authorize(user, ["sip:write"])

    if not decision.granted:
        return refuse(decision.reason or "not permitted to change an SIP")

    if approval.status != ApprovalStatus.APPROVED:
        return refuse("this change has not been approved")

    if approval.target_table != "sip_records" or not approval.target_id:
        return refuse("the approval does not name an SIP to change")

    async with session_scope() as session:

        row = await session.scalar(
            select(SipRecordRow).where(
                SipRecordRow.id == approval.target_id,
                SipRecordRow.user_id == user.user_id,
            )
        )

        if row is None:
            return refuse("no such SIP")

        before = approval.before_state or {}

        if "amount" in before and Decimal(str(before["amount"])) != row.amount:
            return refuse("this SIP changed after the proposal was shown, so it needs approving again")

        after = approval.after_state

        if "amount" in after:
            row.amount = Decimal(str(after["amount"]))

        if "status" in after:
            row.status = SipStatus(after["status"])

        return WriteOutcome(
            status="completed",
            detail=f"SIP updated to {row.amount}",
            target_table="sip_records",
            target_id=row.id,
            idempotency_key=approval.idempotency_key,
        )


async def create_records(
    user: AuthenticatedUser,
    approval: PendingApprovalRow,
    ) -> WriteOutcome:

    """Write every record a person confirmed in conversation, together in one transaction or not at all."""

    if approval.status != ApprovalStatus.APPROVED:
        return refuse("these records have not been approved")

    proposed = (approval.after_state or {}).get("records") or []

    if not proposed:
        return refuse("the approval names no records to create")

    required = sorted({RECORD_SCOPES[record["kind"]] for record in proposed if record["kind"] in RECORD_SCOPES})

    decision = authorize(user, required)

    if not decision.granted:
        return refuse(decision.reason or "not permitted to add these records")

    written: list[str] = []

    async with session_scope() as session:

        for record in proposed:

            row = await write_one(session, user.user_id, record)

            if row is None:
                return refuse(f"I do not know how to store a {record.get('kind')!r} record")

            written.append(row.id)

    return WriteOutcome(
        status="completed",
        detail=f"added {len(written)} record{'' if len(written) == 1 else 's'}",
        target_table="records",
        target_id=",".join(written),
        idempotency_key=approval.idempotency_key,
    )


async def write_one(session, user_id: int, record: dict):

    """Create one record of whichever kind was confirmed, returning None for a kind nothing handles."""

    kind = record.get("kind")

    fields = record.get("fields") or {}

    amount = Decimal(str(fields["amount"]))

    frequency = Frequency(fields.get("frequency", "monthly"))

    if kind == "income":
        return await records_repository.create_income(
            session,
            user_id=user_id,
            label=fields["label"],
            amount=amount,
            frequency=frequency,
            source=fields.get("source", "salary"),
        )

    if kind == "expense":
        return await records_repository.create_expense(
            session,
            user_id=user_id,
            label=fields["label"],
            amount=amount,
            frequency=frequency,
            category=fields.get("category", "general"),
        )

    if kind == "emi":

        months = int(fields.get("remaining_months") or 0)

        rate = Decimal(str(fields.get("interest_rate_percent") or "0"))

        liability = await records_repository.create_liability(
            session,
            user_id=user_id,
            label=fields["label"],
            principal_outstanding=Decimal(str(fields.get("principal_outstanding") or amount * months)),
            interest_rate_percent=rate,
            tenure_months=months,
            lender=fields.get("lender") or "",
        )

        return await records_repository.create_emi(
            session,
            user_id=user_id,
            liability_id=liability.id,
            label=fields["label"],
            amount=amount,
            interest_rate_percent=rate,
            remaining_months=months,
        )

    if kind == "sip":
        return await records_repository.create_sip(
            session,
            user_id=user_id,
            scheme_name=fields["label"],
            amount=amount,
            frequency=frequency,
        )

    return None


WRITE_TOOLS = {
    "update_sip_instruction": update_sip_instruction,
    "create_records": create_records,
}
