"""Policy metadata for the record capture skill, the second skill whose result can reach a write.

It requires approval, and that is the whole design rather than a caution. The rule this backend was
built on is that the conversation never writes: data enters through something a person filled in and
checked. Capturing a figure from a sentence does not abandon that rule, it moves the checking to
where the sentence was said - the skill proposes, a card shows exactly what would be stored, and the
orchestrator writes only after the person presses Add. A misheard "15L" is a card someone declines,
never a record they have to find and delete later.

``write_tool`` names ``create_records`` and this skill cannot call it. Naming and calling stay
separated for the same reason they are separated for the SIP skill: it makes "a model cannot write"
a property of the call graph rather than a promise about behaviour.

The read permissions are here so the skill can see what a person already has. Someone who tells the
planner their salary twice should be told it is already recorded rather than given a second copy, and
that check needs the reads.

One model call is budgeted. Extraction is a structured output call validated against a schema before
anything is proposed - the model turns a sentence into candidate fields and has no say in whether
they are stored.
"""

from app.graphs.skills.contracts import SkillDefinition

DEFINITION = SkillDefinition(
    name="record_capture",
    version="1.0",
    description=(
        "Record a financial fact the person has just stated about themselves. "
        "Use when someone states their salary, rent, a regular expense, a loan EMI or a monthly "
        "SIP - anything phrased as a fact about their own money rather than a question about it."
    ),
    risk_level="medium",
    required_permissions=[
        "income:read",
        "expenses:read",
        "liabilities:read",
        "sip:read",
    ],
    allowed_tools=[],
    read_only=False,
    requires_approval=True,
    quotes_figures=False,
    maximum_model_calls=1,
    maximum_tool_calls=2,
    timeout_seconds=25,
)
