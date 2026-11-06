"""Which tools the agent is given for a turn, picked from the turn's intents."""

from collections.abc import Sequence

from langchain_core.tools import BaseTool

from app.agent.intents import (
    ADD_DATA,
    CHANGE_DATA,
    DELETE_DATA,
    GENERAL_QUESTION,
    GOAL_CHECK,
    MARKET_INFO,
    MISSING_DATA,
    SIMULATION,
    VIEW_DATA,
    )
from app.agent.tools import ALL_TOOLS


ALWAYS_TOOLS = ("list_records", "get_missing_sections")

ADD_TOOLS = (
    "add_family_member",
    "add_income_source",
    "add_expense",
    "add_transaction",
    "add_bank_account",
    "add_fixed_deposit",
    "add_retirement_account",
    "add_physical_asset",
    "add_stock_or_fund",
    "add_sip_plan",
    "search_stocks_and_funds",
    "add_loan",
    "add_credit_card",
    "add_insurance_policy",
    "add_goal",
    "update_profile",
    "set_tax_profile",
    "set_planning_rate",
    "mark_section_status",
    "open_form",
    )

TOOLS_BY_INTENT: dict[str, tuple[str, ...]] = {
    VIEW_DATA: ("get_portfolio_exposure",),
    ADD_DATA: ADD_TOOLS,
    CHANGE_DATA: ("update_record", "update_profile", "set_tax_profile", "set_planning_rate", "link_asset_to_goal", "open_form"),
    DELETE_DATA: ("delete_record",),
    GOAL_CHECK: ("check_goal_progress", "link_asset_to_goal", "add_goal", "set_planning_rate", "open_form"),
    MISSING_DATA: ("mark_section_status",),
    SIMULATION: ("check_goal_progress", "set_planning_rate"),
    MARKET_INFO: (
        "search_stocks_and_funds",
        "get_fund_details",
        "get_stock_details",
        "compare_funds",
        "get_portfolio_exposure",
        ),
    }


def tools_for(intents: Sequence[str]) -> list[BaseTool]:

    """The always-sent tools plus every tool the intents need, in ALL_TOOLS order, or all tools for a general or unknown intent."""

    if not intents or any(intent not in TOOLS_BY_INTENT for intent in intents):
        return list(ALL_TOOLS)

    names = set(ALWAYS_TOOLS)

    for intent in intents:
        names.update(TOOLS_BY_INTENT[intent])

    return [tool for tool in ALL_TOOLS if tool.name in names]
