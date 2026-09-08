"""The tools that compute rather than fetch, and the only place a figure is derived from other figures.

This is the boundary the whole design still rests on, and it did not move when the skills did. The
model may read rows and it may quote what these tools return; it may not do arithmetic. Every derived
number in the product - a surplus, a savings rate, a required monthly contribution, an inflated target
- comes out of a versioned calculator in ``app.calculations`` and arrives here already computed.

That is why these are tools rather than instructions. Telling a model "compute the surplus carefully"
produces a number nobody can trace to a formula; handing it ``cashflow_summary`` produces one stamped
with ``cashflow.v1``, backed by the rows it was built from, and identical to the figure the workspace
panel is drawing at the same moment from the same function.

Each tool records its calculator version on the log, so an answer given today can be explained in a
year. Evidence travels the same way: the rows behind the figure, not a description of them.

``project_goal`` takes a goal id rather than a name, and that is the fix for a specific failure. The
old goal planning skill resolved a name by word overlap and, when nothing matched, silently projected
whichever goal sorted first - so "how are my goals doing" got a confident answer about one of five.
The model now has to call ``list_goals`` and pass an id, which means it has seen the list it is
choosing from.

``cashflow_summary`` returns the blocks too. A cash flow answer is a chart and a table as much as a
sentence, and the model cannot build either - so the tool attaches them and the interface renders them
underneath whatever the model wrote.
"""

from langchain_core.tools import BaseTool, tool

from app.agent.state import AgentContext, RunLog
from app.alerts.service import alert_service
from app.calculations.cashflow.v1 import CALCULATOR_VERSION as CASHFLOW_VERSION
from app.calculations.cashflow.v1 import CashflowInput, run_cashflow
from app.calculations.goals.v1 import CALCULATOR_VERSION as GOALS_VERSION
from app.repositories import get_cashflow_repository
from app.services.projections import project_one
from app.repositories.goals_repository import goals_repository
from app.utils.dates import today_in_timezone


def build_analysis_tools(context: AgentContext, log: RunLog) -> list[BaseTool]:

    """Build every calculating tool bound to this caller, so no figure is derived outside a calculator."""

    cashflow = get_cashflow_repository()

    @tool("cashflow_summary")
    async def cashflow_summary() -> dict:

        """Compute this month's income, committed outflow, surplus and savings rate from stored records."""

        log.used("cashflow_summary")

        records = await cashflow.get_cashflow_records(context.user_id)

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
    async def project_goal(goal_id: str) -> dict:

        """Project one goal - call list_goals first and pass an id, never guess which goal was meant."""

        log.used("project_goal")

        snapshot = await goals_repository.get_snapshot(context.user_id, goal_id)

        if snapshot is None:
            return {"note": f"no goal with id {goal_id} - call list_goals to see what exists"}

        projected = project_one(snapshot, today_in_timezone(context.timezone))

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
    async def check_alerts() -> dict:

        """Report what the planner has noticed unprompted - EMI load, savings rate, goals falling behind."""

        log.used("check_alerts")

        findings = await alert_service.evaluate(context.user_id)

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

    return [cashflow_summary, project_goal, check_alerts]
