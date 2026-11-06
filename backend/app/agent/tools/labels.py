"""The short, friendly line the chat shows for each tool while the planner runs it."""


TOOL_LABELS = {
    "check_goal_progress": "Checking your goal progress",
    "get_missing_sections": "Looking for missing details",
    "mark_section_status": "Noting what you don't have",
    "list_records": "Reading your records",
    "update_record": "Updating a record",
    "delete_record": "Deleting a record",
    "update_profile": "Updating your profile",
    "add_family_member": "Adding a family member",
    "add_income_source": "Adding an income source",
    "add_expense": "Adding an expense",
    "add_transaction": "Adding a transaction",
    "add_bank_account": "Adding a bank account",
    "add_fixed_deposit": "Adding a fixed deposit",
    "add_retirement_account": "Adding a retirement account",
    "add_physical_asset": "Adding an asset",
    "add_stock_or_fund": "Adding a stock or fund",
    "add_sip_plan": "Adding a SIP",
    "search_stocks_and_funds": "Searching stocks and funds",
    "get_fund_details": "Reading the fund's portfolio",
    "get_stock_details": "Reading the stock's details",
    "compare_funds": "Comparing funds",
    "get_portfolio_exposure": "Adding up your sector mix",
    "add_loan": "Adding a loan",
    "add_credit_card": "Adding a credit card",
    "add_insurance_policy": "Adding an insurance policy",
    "add_goal": "Adding a goal",
    "link_asset_to_goal": "Linking money to a goal",
    "set_planning_rate": "Saving a planning rate",
    "set_tax_profile": "Saving your tax details",
    "open_form": "Opening a form",
    }


def label_for(name: str) -> str:

    """Return the friendly line for a tool, or its own name when it has none."""

    return TOOL_LABELS.get(name, name)
