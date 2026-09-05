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
"""

from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select

from app.core.security import AuthenticatedUser, authorize
from app.db.session import session_scope
from app.models.finance import ApprovalStatus, SipStatus
from app.models.orm.credit import SipRecordRow
from app.models.orm.system import PendingApprovalRow


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


WRITE_TOOLS = {
    "update_sip_instruction": update_sip_instruction,
}
