"""The server-side risk policy for every tool: how risky it is and whether the user must approve it first."""

from dataclasses import dataclass
from enum import StrEnum


class Risk(StrEnum):

    """How much harm a tool can do to the user's saved data."""

    read = "read"
    write = "write"
    sensitive = "sensitive"
    destructive = "destructive"


@dataclass(frozen=True)
class ToolPolicy:

    """What the server allows for one tool, decided in code and never by the model."""

    risk: Risk
    approval_required: bool = False


READ = ToolPolicy(Risk.read)
WRITE = ToolPolicy(Risk.write)
SENSITIVE = ToolPolicy(Risk.sensitive)
SENSITIVE_APPROVED = ToolPolicy(Risk.sensitive, approval_required=True)
DESTRUCTIVE_APPROVED = ToolPolicy(Risk.destructive, approval_required=True)

TOOL_POLICIES: dict[str, ToolPolicy] = {
    "list_records": READ,
    "get_missing_data": READ,
    "check_goal_progress": READ,
    "update_data_coverage": WRITE,
    "add_family_member": WRITE,
    "add_income_source": WRITE,
    "add_expense": WRITE,
    "add_transaction": WRITE,
    "add_bank_account": WRITE,
    "add_fixed_deposit": WRITE,
    "add_retirement_account": WRITE,
    "add_physical_asset": WRITE,
    "add_loan": WRITE,
    "add_credit_card": WRITE,
    "add_insurance_policy": WRITE,
    "add_goal": WRITE,
    "update_profile": SENSITIVE,
    "set_tax_profile": SENSITIVE,
    "set_assumption": SENSITIVE,
    "allocate_goal": SENSITIVE,
    "update_record": SENSITIVE_APPROVED,
    "delete_record": DESTRUCTIVE_APPROVED,
    }


def policy_for(tool_name: str) -> ToolPolicy | None:

    """Return the tool's policy, or None for a tool the server does not allow."""

    return TOOL_POLICIES.get(tool_name)


def needs_approval(tool_name: str) -> bool:

    """Say whether the user must approve this tool before it runs."""

    policy = policy_for(tool_name)

    return policy is not None and policy.approval_required
