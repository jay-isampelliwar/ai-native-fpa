"""Policy metadata for goal planning, the first skill built as a manual subgraph.

This skill has a fixed sequence and therefore no agent. Answering "can I reach this goal"
always means the same four steps in the same order: find the goal, read the cash flow, run
the projection, describe the result. There is no branch a model could usefully choose, and
handing the sequence to one would only add a way for it to go wrong.

The permission list is wider than the cash flow summary's because the question genuinely
spans more: a goal projection needs the goal, the assets funding it and the surplus that
could fund it further. Each scope earns its place, and ``goals:write`` is deliberately absent
- this skill plans, and changing a goal is a different skill behind an approval.

``risk_level`` is medium rather than low. Nothing is written, but the output is advice a
person will act on with a large sum over a long horizon, and a wrong assumption here is more
consequential than a wrong spending summary. The level is what decides how much evaluation
the skill needs before it ships, not what the graph does with the result.

Budgets are tight because no model call is needed at all. The skill is deterministic end to
end; the allowance of one call exists only so a future explanation node can be added without
a definition change.
"""

from app.graphs.skills.contracts import SkillDefinition

DEFINITION = SkillDefinition(
    name="goal_planning",
    version="1.0",
    description=(
        "Project a savings goal and report whether it is on track. "
        "Use for questions about affording a house, education, a car or retirement corpus, "
        "how much to invest monthly for a target, or whether a goal will be met on time."
    ),
    risk_level="medium",
    required_permissions=[
        "goals:read",
        "income:read",
        "expenses:read",
        "liabilities:read",
        "sip:read",
        "investments:read",
    ],
    allowed_tools=[],
    read_only=True,
    requires_approval=False,
    maximum_model_calls=1,
    maximum_tool_calls=4,
    timeout_seconds=20,
)
