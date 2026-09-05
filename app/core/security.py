"""Who the caller is, what they are allowed to do, and how one request is traced.

Authentication is deliberately thin. There is no token, no session and no password:
the client sends a ``user_id`` integer and the API layer turns it into an
``AuthenticatedUser``. This is a conscious Phase 1 decision - the product being proven
is the skill orchestration, not the login flow - and it is safe to defer because
nothing downstream parses the identity, it only carries it into the repositories.

Authorization, by contrast, is not deferred. ``authorize`` stays in the graph from day
one because the permission check is a structural edge, not a feature: it is what stops a
hallucinated or injected skill name from reaching data the caller cannot see. During
Phase 1 ``local_user`` grants every scope, so the check passes but the wiring is real;
narrowing scopes later is a change to that one function, not to the graph.

Scope naming is ``<resource>:<action>`` - ``goals:read``, ``sip:write``. Read and write
are separate scopes for the same resource on purpose, because most skills need only the
read half and least privilege is impossible to express otherwise.

``authorize`` returns a decision object rather than raising. The orchestrator needs to
record a refusal in the audit trail and answer the user politely, and an exception
thrown through the middle of a graph node makes both harder.

Correlation identifiers are minted once per request and threaded through state, logs,
traces, checkpoints and audit rows, so one user complaint can be reconstructed end to
end without searching on anything sensitive.
"""

from uuid import uuid4

from pydantic import BaseModel, Field

ALL_SCOPES = frozenset(
    {
        "income:read",
        "expenses:read",
        "goals:read",
        "goals:write",
        "investments:read",
        "sip:read",
        "sip:write",
        "deposits:read",
        "liabilities:read",
        "insurance:read",
        "retirement:read",
        "retirement:write",
        "plan:write",
        "records:archive",
    }
)


class AuthenticatedUser(BaseModel):

    """The caller for one request, identified by nothing more than the user id the client sent."""

    user_id: int
    scopes: frozenset[str] = Field(default_factory=frozenset)


class AuthorizationDecision(BaseModel):

    """The outcome of one permission check, shaped so a refusal can be audited rather than thrown."""

    granted: bool
    missing_scopes: list[str] = Field(default_factory=list)
    reason: str | None = None


def local_user(user_id: int) -> AuthenticatedUser:

    """Build a Phase 1 caller that holds every scope, so the permission wiring runs without a real auth provider."""

    return AuthenticatedUser(user_id=user_id, scopes=ALL_SCOPES)


def new_correlation_id() -> str:

    """Mint the identifier that ties one request's state, logs, traces and audit rows together."""

    return f"req_{uuid4().hex}"


def authorize(
    user: AuthenticatedUser,
    required_permissions: list[str],
    ) -> AuthorizationDecision:

    """Check a skill's required scopes against the caller's held scopes, returning a recordable decision."""

    missing = sorted(scope for scope in required_permissions if scope not in user.scopes)

    if missing:
        return AuthorizationDecision(
            granted=False,
            missing_scopes=missing,
            reason=f"caller is missing required scopes: {', '.join(missing)}",
        )

    return AuthorizationDecision(granted=True)
