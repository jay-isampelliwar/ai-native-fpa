"""The analysis tools: run exact calculations on the user's saved data, so the model never does the maths itself."""

from datetime import date

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage

from app.agent.blocks import goal_progress_block
from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_session
from app.agent.tools.results import ok, to_message
from app.features.analysis.report import goal_progress_report
from app.features.analysis.service import AnalysisService


@tool
async def check_goal_progress(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Check if the user is on track for every active goal: monthly saving needed, money free each month and shortfall, with ready formulas. Read-only. Use it for any goal or shortfall question."""

    async with tool_session(runtime.context) as session:
        progress = await AnalysisService(session).goal_progress(runtime.context.user_id, date.today())

    result = ok(
        "Goal progress is in the report that follows. Its $$ blocks are ready to paste whole.",
        block=goal_progress_block(progress),
        )

    return to_message(result, runtime.tool_call_id, extra_text=goal_progress_report(progress))
