"""Policy metadata for the cash flow summary skill, kept apart from the code that runs it.

The definition lives in its own module so the answer to "what is this skill allowed to
do" can be read without reading the implementation. Reviewers, and the permission node,
only need this file.

The permissions listed are the ones the skill actually reads and no more. It sees income,
expenses, EMIs and SIPs because a surplus figure needs all four; it does not ask for
``goals:read`` or ``investments:read``, so a future change that starts touching holdings
will fail the permission check rather than quietly widening access.

``read_only`` and ``requires_approval`` together place this skill on the graph's safe
path: ``route_by_risk`` sends its results straight to the audit record, and the validator
rejects any result from it that carries a pending approval. A cash flow summary that
tried to change something would be stopped by the orchestrator, not by good intentions
inside the skill.

The budgets are small on purpose. This skill performs one repository read and one
deterministic calculation, so a run that reaches even one model call is a sign the
implementation drifted from the design.
"""

from app.graphs.skills.contracts import SkillDefinition

DEFINITION = SkillDefinition(
    name="cashflow_summary",
    version="1.0",
    description=(
        "Summarise this month's income, committed outflow and free surplus. "
        "Use for questions about salary, spending, savings rate, how much is left over "
        "or whether the month runs at a deficit."
    ),
    risk_level="low",
    required_permissions=[
        "income:read",
        "expenses:read",
        "liabilities:read",
        "sip:read",
    ],
    allowed_tools=[],
    read_only=True,
    requires_approval=False,
    maximum_model_calls=1,
    maximum_tool_calls=2,
    timeout_seconds=15,
)
