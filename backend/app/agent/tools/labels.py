"""The short, friendly line the chat shows for each tool while the planner runs it."""


TOOL_LABELS = {
    "check_goal_progress": "Checking your goal progress",
    "get_missing_data": "Looking for missing details",
    "update_data_coverage": "Updating what we know about you",
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
    "add_loan": "Adding a loan",
    "add_credit_card": "Adding a credit card",
    "add_insurance_policy": "Adding an insurance policy",
    "add_goal": "Adding a goal",
    "allocate_goal": "Linking money to a goal",
    "set_assumption": "Saving a planning assumption",
    "set_tax_profile": "Saving your tax details",
    }


def label_for(name: str) -> str:

    """Return the friendly line for a tool, or its own name when it has none."""

    return TOOL_LABELS.get(name, name)
