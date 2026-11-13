"""Every tool the planner agent can call, gathered into one list for the graph."""

from app.agent.tools.analysis import check_goal_progress
from app.agent.tools.assets import add_bank_account, add_fixed_deposit, add_physical_asset, add_retirement_account
from app.agent.tools.cash_flow import add_expense, add_income_source, add_transaction
from app.agent.tools.investments import add_stock_or_fund, add_sip_plan
from app.agent.tools.forms import open_form
from app.agent.tools.imports import answer_import_question, approve_import, get_import_preview, undo_import
from app.agent.tools.indices import get_index_quote
from app.agent.tools.liabilities import add_credit_card, add_loan
from app.agent.tools.overview import (
    get_asset_split,
    get_cash_flow_history,
    get_financial_health,
    get_month_summary,
    get_net_worth,
    get_upcoming_events,
    )
from app.agent.tools.market import (
    compare_funds,
    get_fund_details,
    get_portfolio_exposure,
    get_stock_details,
    search_stocks_and_funds,
    )
from app.agent.tools.planning import add_goal, link_asset_to_goal, set_planning_rate, set_tax_profile
from app.agent.tools.profile import add_family_member, update_profile
from app.agent.tools.protection import add_insurance_policy
from app.agent.tools.records import (
    delete_record,
    get_missing_sections,
    list_records,
    mark_section_status,
    update_record,
    )
from app.agent.tools.web import web_search


ALL_TOOLS = [
    check_goal_progress,
    get_missing_sections,
    mark_section_status,
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
    add_stock_or_fund,
    add_sip_plan,
    search_stocks_and_funds,
    get_fund_details,
    get_stock_details,
    compare_funds,
    get_portfolio_exposure,
    get_index_quote,
    web_search,
    get_net_worth,
    get_asset_split,
    get_month_summary,
    get_cash_flow_history,
    get_financial_health,
    get_upcoming_events,
    add_loan,
    add_credit_card,
    add_insurance_policy,
    add_goal,
    link_asset_to_goal,
    set_planning_rate,
    set_tax_profile,
    open_form,
    get_import_preview,
    answer_import_question,
    approve_import,
    undo_import,
    ]
