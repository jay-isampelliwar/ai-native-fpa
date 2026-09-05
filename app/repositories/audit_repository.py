"""Persistence for the audit trail, the one table the application only ever appends to.

There is no update and no delete here, and that absence is the design. Evidence that can be
edited is not evidence, so a correction is a new row explaining the earlier one rather than
a rewrite of it. The table has no ``updated_at`` for the same reason.

``write`` takes an already built ``AuditRecord`` rather than graph state. Deciding what goes
into the record is the recorder's job and it is a decision worth keeping in one place;
this class only puts it in a table.

The write runs in its own session rather than joining the caller's. An audit row must
survive the failure of whatever it is describing - a rolled back write still happened and
still owes an explanation - so tying it to the same transaction would delete exactly the
records most worth having.

Queries here are for reconstructing one run or one user's history, both indexed. There is
deliberately no general search: the audit trail is evidence to be looked up by identifier,
not a reporting surface to be mined.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import AuditRecord
from app.db.session import session_scope
from app.models.orm.system import AuditRecordRow


class AuditRepository:

    """Appends audit records and reads them back by correlation id or by user."""

    async def write(self, record: AuditRecord) -> None:

        """Append one record in its own transaction, so it survives the failure it may be describing."""

        async with session_scope() as session:
            session.add(self._to_row(record))

    async def by_correlation(self, correlation_id: str) -> list[AuditRecord]:

        """Fetch every record written under one request identifier, for reconstructing a single run."""

        async with session_scope() as session:
            rows = await session.scalars(
                select(AuditRecordRow)
                .where(AuditRecordRow.correlation_id == correlation_id)
                .order_by(AuditRecordRow.recorded_at)
            )

            return [self._to_record(row) for row in rows]

    async def recent_for_user(self, user_id: int, limit: int = 50) -> list[AuditRecord]:

        """Fetch a user's most recent runs, newest first, for answering questions about their history."""

        async with session_scope() as session:
            rows = await session.scalars(
                select(AuditRecordRow)
                .where(AuditRecordRow.user_id == user_id)
                .order_by(AuditRecordRow.recorded_at.desc())
                .limit(limit)
            )

            return [self._to_record(row) for row in rows]

    def _to_row(self, record: AuditRecord) -> AuditRecordRow:

        """Map the audit record onto its table row, keeping identifiers and versions only."""

        return AuditRecordRow(
            correlation_id=record.correlation_id,
            user_id=record.user_id,
            conversation_id=record.conversation_id,
            recorded_at=record.recorded_at,
            skill_name=record.skill_name,
            skill_version=record.skill_version,
            route_confidence=record.route_confidence,
            route_reason=record.route_reason,
            permission_granted=record.permission_granted,
            denial_reason=record.denial_reason,
            result_status=record.result_status,
            evidence_ids=record.evidence_ids,
            calculator_versions=record.calculator_versions,
            assumptions=record.assumptions,
            validation_errors=record.validation_errors,
            approval_id=record.pending_approval_id,
            approval_decision=record.approval_decision,
            write_performed=record.write_performed,
        )

    def _to_record(self, row: AuditRecordRow) -> AuditRecord:

        """Map a stored row back to the audit record shape callers already work with."""

        return AuditRecord(
            correlation_id=row.correlation_id,
            user_id=row.user_id,
            conversation_id=row.conversation_id,
            recorded_at=row.recorded_at,
            skill_name=row.skill_name,
            skill_version=row.skill_version,
            route_confidence=float(row.route_confidence) if row.route_confidence is not None else None,
            route_reason=row.route_reason,
            permission_granted=row.permission_granted,
            denial_reason=row.denial_reason,
            result_status=row.result_status,
            evidence_ids=list(row.evidence_ids),
            calculator_versions=list(row.calculator_versions),
            assumptions=dict(row.assumptions),
            validation_errors=list(row.validation_errors),
            approval_decision=row.approval_decision,
            pending_approval_id=row.approval_id,
            write_performed=row.write_performed,
        )


audit_repository = AuditRepository()
