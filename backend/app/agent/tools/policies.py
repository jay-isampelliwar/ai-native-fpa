"""The server-side risk policy for every tool: how risky it is and whether the user must approve it first."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.features.assets.fund_houses import is_shared_brand


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
    "get_missing_sections": READ,
    "check_goal_progress": READ,
    "search_stocks_and_funds": READ,
    "get_fund_details": READ,
    "get_stock_details": READ,
    "compare_funds": READ,
    "get_portfolio_exposure": READ,
    "get_index_quote": READ,
    "web_search": READ,
    "get_net_worth": READ,
    "get_asset_split": READ,
    "get_month_summary": READ,
    "get_cash_flow_history": READ,
    "get_financial_health": READ,
    "get_upcoming_events": READ,
    "open_form": READ,
    "mark_section_status": WRITE,
    "add_family_member": WRITE,
    "add_income_source": WRITE,
    "add_expense": WRITE,
    "add_transaction": WRITE,
    "add_bank_account": WRITE,
    "add_fixed_deposit": WRITE,
    "add_retirement_account": WRITE,
    "add_physical_asset": WRITE,
    "add_stock_or_fund": WRITE,
    "add_sip_plan": WRITE,
    "add_loan": WRITE,
    "add_credit_card": WRITE,
    "add_insurance_policy": WRITE,
    "add_goal": WRITE,
    "update_profile": SENSITIVE,
    "set_tax_profile": SENSITIVE,
    "set_planning_rate": SENSITIVE,
    "link_asset_to_goal": SENSITIVE,
    "update_record": SENSITIVE_APPROVED,
    "delete_record": DESTRUCTIVE_APPROVED,
    "get_import_preview": READ,
    "answer_import_question": WRITE,
    "approve_import": SENSITIVE_APPROVED,
    "undo_import": DESTRUCTIVE_APPROVED,
    }


def units_to_confirm(arguments: dict[str, Any]) -> bool:

    """True when a holding has an amount but no units, so the app works out units and the user must confirm them."""

    return arguments.get("units") is None and arguments.get("amount") is not None and bool(arguments.get("isin"))


def bank_to_confirm(arguments: dict[str, Any]) -> bool:

    """True when a deposit's bank also runs mutual funds, such as Axis or HDFC, so the user must say it is a bank deposit."""

    return is_shared_brand(arguments.get("bank_name"))


CONFIRM_RULES: dict[str, Callable[[dict[str, Any]], bool]] = {
    "add_stock_or_fund": units_to_confirm,
    "add_fixed_deposit": bank_to_confirm,
    }


def policy_for(tool_name: str) -> ToolPolicy | None:

    """Return the tool's policy, or None for a tool the server does not allow."""

    return TOOL_POLICIES.get(tool_name)


def needs_approval(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    ) -> bool:

    """Say whether the user must approve this call before it runs: always for some tools, and for others only with some arguments."""

    policy = policy_for(tool_name)

    if policy is None:
        return False

    if policy.approval_required:
        return True

    rule = CONFIRM_RULES.get(tool_name)

    return rule is not None and arguments is not None and rule(arguments)
