"""The evidence trail for one request, written whether it succeeded, was refused or failed.

An audit record answers a question a user or a regulator may ask months later: on what
data, using which version of which formula, under whose approval, did the system say
this. Producing that answer after the fact is impossible unless the versions were
captured at the time, so every field here is written at the moment of the run.

What is recorded is deliberately thin. Identifiers, versions, decisions and outcomes -
never balances, transaction narratives, account numbers or raw model output.
``evidence_ids`` point at rows in the application database, so a reviewer can fetch the
underlying records through the same permission checks as anyone else rather than reading
them out of a log they should not have access to.

Refusals are recorded as carefully as successes. A permission denial, an unroutable
message and a rejected approval are all outcomes worth seeing, and a system that only
logs its successes cannot be audited at all.

Persistence is intentionally behind ``AuditRecorder`` rather than inlined. Phase 1 emits
structured logs; the database backed recorder replaces this class without any node
changing, because nodes only ever call ``record``.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.graphs.orchestrator.state import PlannerState


class AuditRecord(BaseModel):

    """One immutable row describing how a single request was routed, decided and completed."""

    correlation_id: str
    user_id: int
    conversation_id: str
    recorded_at: datetime

    skill_name: str | None = None
    skill_version: str | None = None
    route_confidence: float | None = None
    route_reason: str | None = None

    permission_granted: bool = False
    denial_reason: str | None = None

    result_status: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: dict[str, float] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)

    approval_decision: str | None = None
    pending_approval_id: str | None = None
    write_performed: bool = False


class AuditRecorder:

    """Builds an audit record from finished graph state and persists it behind one replaceable method."""

    async def record(self, state: PlannerState) -> AuditRecord:

        """Capture the run as an immutable record and persist it, returning what was written."""

        record = self.build(state)

        await self.persist(record)

        return record

    def build(self, state: PlannerState) -> AuditRecord:

        """Flatten graph state into the audit shape, taking only identifiers, versions and decisions."""

        return AuditRecord(
            correlation_id=state.context.correlation_id if state.context else "unknown",
            user_id=state.user_id,
            conversation_id=state.conversation_id,
            recorded_at=datetime.now(UTC),
            skill_name=state.skill_name,
            skill_version=state.definition.version if state.definition else None,
            route_confidence=state.route_confidence,
            route_reason=state.route_reason,
            permission_granted=state.permission_granted,
            denial_reason=state.denial_reason,
            result_status=state.result.status if state.result else None,
            evidence_ids=state.result.evidence_ids if state.result else [],
            assumptions=state.result.assumptions if state.result else {},
            validation_errors=state.validation_errors,
            approval_decision=state.approval_decision,
            pending_approval_id=state.result.pending_approval_id if state.result else None,
            write_performed=state.write_outcome is not None,
        )

    async def persist(self, record: AuditRecord) -> None:

        """Write the record to durable storage, replaced by the database backed recorder in Phase 5."""

        print(record.model_dump_json())


recorder = AuditRecorder()
