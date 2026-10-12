"""The analysis tools: run exact calculations on the user's saved data, so the model never does the maths itself."""

from datetime import date

from langchain.tools import ToolRuntime, tool

from app.agent.context import PlannerContext
from app.db.session import SessionLocal
from app.features.analysis.report import goal_progress_report
from app.features.analysis.service import AnalysisService


@tool
async def check_goal_progress(runtime: ToolRuntime[PlannerContext]) -> str:

    """Check if the user is on track for every active goal: monthly need, money available and shortfall, with ready formulas."""

    async with SessionLocal() as session:
        progress = await AnalysisService(session).goal_progress(runtime.context.user_id, date.today())

    return goal_progress_report(progress)
