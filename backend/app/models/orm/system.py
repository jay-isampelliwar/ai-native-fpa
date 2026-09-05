"""Tables that describe the service's own behaviour rather than a user's money.

``UserRow`` is deliberately thin. Phase 1 identifies a caller by an integer and nothing
else, so this table exists to give that integer a foreign key target and a place to keep
locale, not to become an identity provider. When real authentication arrives, credentials
belong beside it or outside it, never in it.

``AuditRecordRow`` is append only by convention and by shape. It has no ``updated_at``
because a record that can be updated is not evidence, and its columns hold identifiers,
versions and decisions - the ``evidence_ids`` array points at rows rather than copying
them, so reading the audit trail never exposes financial data the reader could not already
see through the normal permission checks.

``PendingApprovalRow`` is the durable half of the ``interrupt`` in the graph. LangGraph's
checkpoint holds where the run paused; this table holds what the user was actually shown,
because ``before_state`` and ``after_state`` are what an approval is binding to. If the
underlying record changes while the approval waits, the stored before state is what proves
the proposal is now stale.

``idempotency_key`` is unique at the database level rather than checked in code. Two
processes racing on the same approval both attempt the insert and exactly one wins, which
is a guarantee an application level check cannot make.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecordId
from app.models.finance import ApprovalStatus
from app.models.orm.enums import APPROVAL_STATUS


class UserRow(Base):

    """One planner user, holding the locale every calculation and reply is rendered in."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class AuditRecordRow(Base):

    """One immutable account of how a request was routed, decided and completed."""

    __tablename__ = "audit_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    skill_name: Mapped[str | None] = mapped_column(Text)
    skill_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(Text)

    route_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    route_reason: Mapped[str | None] = mapped_column(Text)

    permission_granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    denial_reason: Mapped[str | None] = mapped_column(Text)

    result_status: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    calculator_versions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    assumptions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validation_errors: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    approval_id: Mapped[str | None] = mapped_column(Text)
    approval_decision: Mapped[str | None] = mapped_column(Text)
    write_performed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PendingApprovalRow(Base):

    """A proposed change waiting on a human, storing exactly what they were shown."""

    __tablename__ = "pending_approvals"

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)

    skill_name: Mapped[str] = mapped_column(Text, nullable=False)
    skill_version: Mapped[str] = mapped_column(Text, nullable=False)

    action_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_table: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)

    before_state: Mapped[dict | None] = mapped_column(JSONB)
    after_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    status: Mapped[ApprovalStatus] = mapped_column(
        APPROVAL_STATUS,
        nullable=False,
        default=ApprovalStatus.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column()
    decided_by_user_id: Mapped[int | None] = mapped_column(BigInteger)
