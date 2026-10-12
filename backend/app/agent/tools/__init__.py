"""Every tool the planner agent can call, gathered into one list for the graph."""

from app.agent.tools.analysis import check_goal_progress
from app.agent.tools.assets import add_bank_account, add_fixed_deposit, add_physical_asset, add_retirement_account
from app.agent.tools.cash_flow import add_expense, add_income_source, add_transaction
from app.agent.tools.liabilities import add_credit_card, add_loan
from app.agent.tools.planning import add_goal, allocate_goal, set_assumption, set_tax_profile
from app.agent.tools.profile import add_family_member, update_profile
from app.agent.tools.protection import add_insurance_policy
from app.agent.tools.records import (
    delete_record,
    get_missing_data,
    list_records,
    update_data_coverage,
    update_record,
    )


ALL_TOOLS = [
    check_goal_progress,
    get_missing_data,
    update_data_coverage,
    list_records,
    update_record,
    delete_record,
    update_profile,
    add_family_member,
    add_income_source,
    add_expense,
    add_transaction,
    add_bank_account,
    add_fixed_deposit,
    add_retirement_account,
    add_physical_asset,
    add_loan,
    add_credit_card,
    add_insurance_policy,
    add_goal,
    allocate_goal,
    set_assumption,
    set_tax_profile,
    ]
