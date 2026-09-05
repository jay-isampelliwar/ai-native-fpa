"""Policy metadata for the orientation skill, the one skill that reports on the service rather than the records.

It reads the same four record types the cash flow summary does, and for the same reason: the useful
half of "what do you need from me" is which of those a person has not given yet. It asks for nothing
beyond them, so a later change that starts reading holdings or goals fails the permission check
rather than quietly widening what a greeting can see.

``quotes_figures`` is False, and this is the skill that field exists for. The validator requires
evidence identifiers behind any answered result, because a figure nobody can trace is exactly the
failure this design is built to prevent. An orientation answer quotes no figure - it says what the
planner can do and what is missing - so the rule would reject a correct answer for lacking evidence
it never claimed to have. Turning it off here is narrow and visible; weakening the rule for every
skill would not be.

There are no model calls. What this skill says is assembled from the registry and from record counts,
so the description of what the planner can do cannot drift from what it actually has registered.
"""

from app.graphs.skills.contracts import SkillDefinition

DEFINITION = SkillDefinition(
    name="orientation",
    version="1.0",
    description=(
        "Explain what this planner can do and which records it still needs from the person. "
        "Use for greetings, for questions about the assistant itself or its capabilities, for "
        "anyone asking what information to provide or how to get started, and for any request "
        "that is not about a specific financial figure."
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
    quotes_figures=False,
    maximum_model_calls=0,
    maximum_tool_calls=1,
    timeout_seconds=10,
)
