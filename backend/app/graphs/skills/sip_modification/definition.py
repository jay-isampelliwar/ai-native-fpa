"""Policy metadata for SIP modification, the first skill that can change a record.

This is the skill the whole approval design exists for. It reads, it calculates, and it proposes
- and then the graph stops. ``requires_approval`` is True and ``read_only`` is False, which
together put it on the only path that reaches a controlled write.

``sip:write`` is in the permission list, and that scope is checked twice: once before the skill
runs, and again inside the write tool after approval. The second check is not redundant. A
proposal can wait fifteen minutes, and a caller's scopes can change in that window.

``risk_level`` is high because the action is irreversible from the user's point of view - a
changed mandate debits a different amount next month whether or not anyone noticed. The level
governs how much evaluation the skill needs before shipping, not what the graph does with it.

The skill never sets ``status="completed"``. It returns ``proposed`` with a ``write_tool`` name
and a ``pending_approval_id``, and the validator rejects any result from a skill requiring
approval that claims to have completed a write.
"""

from app.graphs.skills.contracts import SkillDefinition

DEFINITION = SkillDefinition(
    name="sip_modification",
    version="1.0",
    description=(
        "Propose a change to an existing SIP amount, or pause or stop one. "
        "Use when the user asks to increase, decrease, raise, cut, pause or stop a SIP, "
        "or to change how much they invest each month in a scheme."
    ),
    risk_level="high",
    required_permissions=["sip:read", "sip:write", "income:read", "expenses:read", "liabilities:read"],
    allowed_tools=["update_sip_instruction"],
    read_only=False,
    requires_approval=True,
    maximum_model_calls=1,
    maximum_tool_calls=4,
    timeout_seconds=20,
)
