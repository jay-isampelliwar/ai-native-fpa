from langchain_core.tools import BaseTool, tool

from app.agent.state import AgentContext, RunLog
from app.repositories import get_cashflow_repository, get_expense_repository
from app.repositories.goals_repository import goals_repository
from app.repositories.holdings_repository import holdings_repository

DESCRIPTION_LIMIT = 120

TRANSACTION_LIMIT = 50


def build_read_tools(context: AgentContext, log: RunLog) -> list[BaseTool]:

    """Build every lookup tool bound to this caller, leaving the model no way to name another."""

    cashflow = get_cashflow_repository()

    expenses = get_expense_repository()

    @tool("list_income")
    async def list_income() -> dict:

        """List this person's income records with their amounts and how often each arrives."""

        log.used("list_income")

        records = await cashflow.get_cashflow_records(context.user_id)

        if not records.income:
            return {"income": [], "note": "no income records yet"}

        return {
            "income": [
                {
                    "id": record.id,
                    "label": record.label,
                    "amount": str(record.amount),
                    "frequency": record.frequency.value,
                    "monthly_equivalent": str(record.monthly_amount),
                    "source": record.source,
                }
                for record in records.income
            ]
        }

    @tool("list_expenses")
    async def list_expenses() -> dict:

        """List this person's recurring expense records with their amounts and categories."""

        log.used("list_expenses")

        records = await cashflow.get_cashflow_records(context.user_id)

        if not records.expenses:
            return {"expenses": [], "note": "no expense records yet"}

        return {
            "expenses": [
                {
                    "id": record.id,
                    "label": record.label,
                    "amount": str(record.amount),
                    "frequency": record.frequency.value,
                    "monthly_equivalent": str(record.monthly_amount),
                    "category": record.category,
                }
                for record in records.expenses
            ]
        }

    @tool("list_emis")
    async def list_emis() -> dict:

        """List this person's loan EMIs with the amount, interest rate and months remaining on each."""

        log.used("list_emis")

        records = await cashflow.get_cashflow_records(context.user_id)

        if not records.emis:
            return {"emis": [], "note": "no loan EMIs on record yet"}

        return {
            "emis": [
                {
                    "id": record.id,
                    "label": record.label,
                    "amount": str(record.amount),
                    "interest_rate_percent": str(record.interest_rate_percent),
                    "remaining_months": record.remaining_months,
                    "liability_id": record.liability_id,
                }
                for record in records.emis
            ]
        }

    @tool("list_sips")
    async def list_sips() -> dict:

        """List this person's SIPs with the scheme name, amount, frequency and which goal each funds."""

        log.used("list_sips")

        records = await cashflow.get_cashflow_records(context.user_id)

        if not records.sips:
            return {"sips": [], "note": "no SIPs on record yet"}

        return {
            "sips": [
                {
                    "id": record.id,
                    "scheme_name": record.scheme_name,
                    "amount": str(record.amount),
                    "frequency": record.frequency.value,
                    "monthly_equivalent": str(record.monthly_amount),
                    "folio_id": record.folio_id,
                    "linked_goal_id": record.linked_goal_id,
                }
                for record in records.sips
            ]
        }

    @tool("list_goals")
    async def list_goals() -> dict:

        """List this person's savings goals with the target amount, target date and what is funding each."""

        log.used("list_goals")

        snapshots = await goals_repository.list_snapshots(context.user_id)

        if not snapshots:
            return {"goals": [], "note": "no goals set up yet"}

        return {
            "goals": [
                {
                    "id": snapshot.id,
                    "label": snapshot.label,
                    "kind": snapshot.kind,
                    "target_amount": str(snapshot.target_amount),
                    "target_date": snapshot.target_date.isoformat(),
                    "priority": snapshot.priority,
                    "funded_corpus": str(snapshot.funded_corpus),
                    "monthly_contribution": str(snapshot.monthly_contribution),
                }
                for snapshot in snapshots
            ]
        }

    @tool("list_holdings")
    async def list_holdings() -> dict:

        """List the positions this person owns, valued as their last imported statement stated."""

        log.used("list_holdings")

        summary = await holdings_repository.summary(context.user_id)

        if summary.count == 0:
            return {"holdings": [], "note": "no holdings imported yet"}

        return {
            "as_of": summary.valued_at,
            "total_value": str(summary.current_value),
            "total_invested": str(summary.invested_value),
            "holdings": [
                {
                    "id": holding.id,
                    "instrument_name": holding.instrument_name,
                    "isin": holding.isin,
                    "asset_type": holding.asset_type,
                    "units": str(holding.units),
                    "average_cost": str(holding.average_cost),
                    "invested_value": str(holding.invested_value) if holding.invested_value else None,
                    "current_value": str(holding.current_value) if holding.current_value else None,
                    "as_of": holding.as_of,
                }
                for holding in summary.holdings
            ],
        }

    @tool("list_transactions")
    async def list_transactions(
        year: int,
        month: int,
        category: str | None = None,
        limit: int = 10,
        ) -> dict:

        """List this person's dated spends for one month, newest first, optionally filtered by category."""

        log.used("list_transactions")

        rows = await expenses.list_transactions(
            context.user_id,
            year=year,
            month=month,
            category=category,
            limit=min(limit, TRANSACTION_LIMIT),
        )

        return {
            "year": year,
            "month": month,
            "transactions": [
                {
                    "id": row.id,
                    "occurred_on": row.occurred_on.isoformat(),
                    "amount": str(row.amount),
                    "category": row.category,
                    "merchant": row.merchant,
                    "untrusted_description": row.description[:DESCRIPTION_LIMIT],
                }
                for row in rows
            ],
        }

    @tool("spending_by_category")
    async def spending_by_category(year: int, month: int) -> dict:

        """Total this person's spending per category for one month, highest first."""

        log.used("spending_by_category")

        totals = await expenses.category_totals(context.user_id, year, month)

        return {
            "year": year,
            "month": month,
            "totals": {category: str(amount) for category, amount in totals.items()},
        }

    return [
        list_income,
        list_expenses,
        list_emis,
        list_sips,
        list_goals,
        list_holdings,
        list_transactions,
        spending_by_category,
    ]
