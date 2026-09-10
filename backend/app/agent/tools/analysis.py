"""The tools that compute rather than fetch, so no figure is ever derived outside a versioned calculator."""

from langchain_core.tools import tool

from app.alerts.service import alert_service
from app.calculations.cashflow.v1 import CALCULATOR_VERSION as CASHFLOW_VERSION
from app.calculations.cashflow.v1 import CashflowInput, run_cashflow
from app.calculations.goals.v1 import CALCULATOR_VERSION as GOALS_VERSION
from app.repositories import get_cashflow_repository
from app.repositories.goals_repository import goals_repository
from app.services.projections import project_one
from app.utils.dates import today_in_timezone

DEFAULT_TIMEZONE = "Asia/Kolkata"


@tool("cashflow_summary")
async def cashflow_summary(user_id: int) -> dict:

    """Compute this month's income, committed outflow, surplus and savings rate from stored records."""

    records = await get_cashflow_repository().get_cashflow_records(user_id)

    if not records.evidence_ids:
        return {"note": "no income or expense records yet, so there is no cash flow to compute"}

    result = run_cashflow(
        CashflowInput(
            income=[record.monthly_amount for record in records.income],
            expenses=[record.monthly_amount for record in records.expenses],
            emis=[record.monthly_amount for record in records.emis],
            sips=[record.monthly_amount for record in records.sips],
        )
    )

    return {
        "calculator": CASHFLOW_VERSION,
        "total_income": str(result.total_income),
        "total_expenses": str(result.total_expenses),
        "total_emis": str(result.total_emis),
        "total_sips": str(result.total_sips),
        "committed_outflow": str(result.committed_outflow),
        "free_surplus": str(result.free_surplus),
        "investable_surplus": str(result.investable_surplus),
        "savings_rate_percent": str(result.savings_rate_percent),
        "warnings": result.warnings,
    }


@tool("project_goal")
async def project_goal(
    user_id: int,
    goal_id: str,
    timezone: str = DEFAULT_TIMEZONE,
    ) -> dict:

    """Project one goal - call list_goals first and pass an id, never guess which goal was meant."""

    snapshot = await goals_repository.get_snapshot(user_id, goal_id)

    if snapshot is None:
        return {"note": f"no goal with id {goal_id} - call list_goals to see what exists"}

    projected = project_one(snapshot, today_in_timezone(timezone))

    projection = projected.projection

    return {
        "calculator": GOALS_VERSION,
        "goal": snapshot.label,
        "target_today": str(snapshot.target_amount),
        "target_date": snapshot.target_date.isoformat(),
        "months_remaining": projection.months_remaining,
        "target_at_maturity": str(projection.target_at_maturity),
        "projected_corpus": str(projection.projected_corpus),
        "shortfall": str(projection.shortfall),
        "required_monthly": str(projection.required_monthly),
        "on_track": projection.on_track,
        "funding_valued_at_cost": snapshot.valued_at_cost,
        "warnings": projection.warnings,
    }


@tool("check_alerts")
async def check_alerts(user_id: int) -> dict:

    """Report what the planner has noticed unprompted - EMI load, savings rate, goals falling behind."""

    findings = await alert_service.evaluate(user_id)

    if not findings:
        return {"alerts": [], "note": "nothing is flagged right now"}

    return {
        "alerts": [
            {
                "kind": alert.kind,
                "severity": alert.severity,
                "title": alert.title,
                "detail": alert.detail,
            }
            for alert in findings
        ]
    }


ANALYSIS_TOOLS = [cashflow_summary, project_goal, check_alerts]
