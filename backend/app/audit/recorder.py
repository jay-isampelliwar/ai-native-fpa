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

Refusals are recorded as carefully as successes. A refusal, an agent that ran out of steps and a
tool that declined are all outcomes worth seeing, and a system that only logs its successes cannot be
audited at all.

The columns kept their old names while what fills them changed, which is a deliberate choice to avoid
a migration for a rename. ``skill_name`` now holds the first tool a turn called, ``route_reason``
holds the whole sequence of them, and ``write_performed`` is true when any tool changed a row. A
reader of the table sees what a turn did; a reader of the schema sees the vocabulary of the design
that came before it, and this paragraph is the bridge between the two.

Persistence is intentionally behind ``AuditRecorder`` rather than inlined, and nodes only
ever call ``record``. It writes to the ``audit_records`` table, and a write that cannot land
is dropped rather than retried or held anywhere else.

A failed audit write does not raise. The alternative - propagating the error - would turn a
bookkeeping outage into a service outage, and the request being described has already
happened either way.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.agent.state import PlannerState


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
    calculator_versions: list[str] = Field(default_factory=list)
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
            skill_name=state.tools_used[0] if state.tools_used else None,
            skill_version=None,
            route_confidence=None,
            route_reason=describe_run(state),
            permission_granted=state.denial_reason is None,
            denial_reason=state.denial_reason,
            result_status=status_of(state),
            evidence_ids=state.evidence_ids,
            calculator_versions=state.calculator_versions,
            assumptions={
                key: value
                for key, value in state.assumptions.items()
                if isinstance(value, (int, float))
            },
            validation_errors=[],
            approval_decision=None,
            pending_approval_id=None,
            write_performed=bool(state.writes_performed),
        )

    async def persist(self, record: AuditRecord) -> None:

        """Append the record to the audit table, dropping the record if that write fails."""

        from app.repositories.audit_repository import audit_repository

        try:
            await audit_repository.write(record)

        except Exception:
            pass


def describe_run(state: PlannerState) -> str:

    """Say what this turn actually did, since there is no single routed skill left to name."""

    if state.denial_reason:
        return f"refused: {state.denial_reason}"

    parts = []

    if state.tools_used:
        parts.append(f"called {', '.join(state.tools_used)}")

    if state.writes_performed:
        parts.append(f"changed {'; '.join(state.writes_performed)}")

    return " and ".join(parts) or "answered without calling a tool"


def status_of(state: PlannerState) -> str:

    """Classify the turn the way the old result status did, from what the agent left in state."""

    if state.denial_reason:
        return "refused"

    if state.writes_performed:
        return "completed"

    return "answered" if state.response else "failed"


recorder = AuditRecorder()
