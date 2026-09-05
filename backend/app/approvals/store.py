"""The durable record of what a user was shown and what they decided about it.

LangGraph's checkpoint knows where a run paused. This table knows what the pause was *about* -
which record, which fields, the exact before and after a person saw on screen. Those are
different facts and only one of them is evidence: an approval that cannot say what was proposed
is not an approval, it is a timestamp.

``before_state`` is captured when the proposal is created, not when it executes. Between those
two moments a user may edit the underlying record in another tab, and comparing the stored
before against the row at execution time is what turns that into a refusal rather than a silent
overwrite of someone's newer change.

``idempotency_key`` is unique in the database. Two processes racing on the same approval both
attempt the insert and exactly one wins, which is a guarantee an application level check cannot
make. The key is derived from the approval, so a retry of the same decision is the same key.

Expiry is checked on read rather than swept by a job. A proposal built on a surplus figure from
an hour ago should not execute on today's records without being re-shown, and marking it expired
at the moment someone tries to use it needs no scheduler to be correct.

Nothing here decides whether a change is allowed. That is the permission layer's job and it runs
again at execution time; this module only records what was proposed and what was answered.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import session_scope
from app.models.finance import ApprovalStatus
from app.models.orm.system import PendingApprovalRow


class ApprovalStore:

    """Creates, reads and decides pending approvals, keeping what was shown beside what was decided."""

    async def create(
        self,
        session: AsyncSession,
        user_id: int,
        conversation_id: str,
        correlation_id: str,
        skill_name: str,
        skill_version: str,
        action_kind: str,
        after_state: dict,
        before_state: dict | None = None,
        target_table: str | None = None,
        target_id: str | None = None,
        evidence_ids: list[str] | None = None,
        ) -> PendingApprovalRow:

        """Record a proposal exactly as the user will see it, with an expiry and an idempotency key."""

        approval_id = f"appr_{uuid4().hex[:12]}"

        row = PendingApprovalRow(
            id=approval_id,
            user_id=user_id,
            conversation_id=conversation_id,
            correlation_id=correlation_id,
            skill_name=skill_name,
            skill_version=skill_version,
            action_kind=action_kind,
            target_table=target_table,
            target_id=target_id,
            before_state=before_state,
            after_state=after_state,
            evidence_ids=evidence_ids or [],
            status=ApprovalStatus.PENDING,
            idempotency_key=f"{approval_id}:{action_kind}",
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.approval_expiry_seconds),
        )

        session.add(row)

        await session.flush()

        return row

    async def get(self, approval_id: str, user_id: int) -> PendingApprovalRow | None:

        """Read one approval this user owns, marking it expired if its window has passed."""

        async with session_scope() as session:

            row = await session.scalar(
                select(PendingApprovalRow).where(
                    PendingApprovalRow.id == approval_id,
                    PendingApprovalRow.user_id == user_id,
                )
            )

            if row is None:
                return None

            if row.status == ApprovalStatus.PENDING and row.expires_at < datetime.now(UTC):
                row.status = ApprovalStatus.EXPIRED

            return row

    async def latest_for_conversation(self, conversation_id: str, user_id: int) -> PendingApprovalRow | None:

        """Find the proposal a paused conversation is waiting on, which is what a client approves."""

        async with session_scope() as session:

            return await session.scalar(
                select(PendingApprovalRow)
                .where(
                    PendingApprovalRow.conversation_id == conversation_id,
                    PendingApprovalRow.user_id == user_id,
                    PendingApprovalRow.status == ApprovalStatus.PENDING,
                )
                .order_by(PendingApprovalRow.created_at.desc())
            )

    async def decide(
        self,
        approval_id: str,
        user_id: int,
        decision: str,
        ) -> PendingApprovalRow | None:

        """Record a human decision, refusing anything that is not still pending and unexpired."""

        async with session_scope() as session:

            row = await session.scalar(
                select(PendingApprovalRow).where(
                    PendingApprovalRow.id == approval_id,
                    PendingApprovalRow.user_id == user_id,
                )
            )

            if row is None:
                return None

            if row.status != ApprovalStatus.PENDING:
                return row

            if row.expires_at < datetime.now(UTC):
                row.status = ApprovalStatus.EXPIRED

                return row

            row.status = ApprovalStatus.APPROVED if decision == "approve" else ApprovalStatus.REJECTED
            row.decided_at = datetime.now(UTC)
            row.decided_by_user_id = user_id

            return row


approval_store = ApprovalStore()
