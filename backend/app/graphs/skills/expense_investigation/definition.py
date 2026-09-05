"""Policy metadata for the expense investigation skill, the first one that uses an agent loop.

This skill exists because its question genuinely needs one. "Why did I spend more last
month" cannot be answered by a fixed sequence: the second query depends on what the first
returned, and which category to drill into is not known until the totals come back. That
is the narrow case the implementation guide reserves ``create_agent`` for.

Everything around the loop is still fixed. ``allowed_tools`` names the three reads the
agent may bind and nothing else, so the model chooses the order of its questions but not
the set. Adding a tool to the implementation without adding it here means the skill fails
its own contract rather than quietly gaining a capability.

``read_only`` is True and the permission list contains only ``expenses:read``. An
investigation that ever needed to change something would be the wrong skill: the graph's
validator rejects any result from a read only skill that proposes an approval, so a drift
in that direction fails loudly rather than being caught in review.

The budgets are what stop an agent loop from becoming an unbounded one. Six model calls
and eight tool calls are enough to look at a month, drill into two categories and compare
against the previous month; a run that wants more has stopped investigating and started
wandering, and the orchestrator kills it.
"""

from app.graphs.skills.contracts import SkillDefinition

DEFINITION = SkillDefinition(
    name="expense_investigation",
    version="1.0",
    description=(
        "Investigate and explain a change in spending. "
        "Use for questions about why spending rose or fell, what an unusual charge was, "
        "which categories moved, or where the money went in a given month."
    ),
    risk_level="low",
    required_permissions=["expenses:read"],
    allowed_tools=[
        "spending_by_category",
        "list_transactions",
        "compare_months",
    ],
    read_only=True,
    requires_approval=False,
    maximum_model_calls=6,
    maximum_tool_calls=8,
    timeout_seconds=45,
)
