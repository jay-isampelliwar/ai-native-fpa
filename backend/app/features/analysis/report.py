"""Write goal progress results as plain lines and ready-made $$ formulas, built only from computed numbers."""

from app.calc.goals import GoalResult
from app.calc.money import indian_number
from app.features.analysis.service import GoalProgress


RUPEE_TEX = r"\text{₹}"


def inr(value: float) -> str:

    """Write a rupee amount for plain text, such as ₹10,00,000."""

    return f"₹{indian_number(value)}"


def inr_tex(value: float) -> str:

    """Write a rupee amount for KaTeX, keeping the commas from adding space."""

    return RUPEE_TEX + indian_number(value).replace(",", "{,}")


def rate_tex(pct: float) -> str:

    """Write a percent rate as a decimal, so 6.5 becomes 0.065."""

    return f"{pct / 100:g}"


def cash_flow_formula(progress: GoalProgress) -> str:

    """Return the $$ block that shows how the free monthly money was found."""

    flow = progress.cash_flow

    return "\n".join(
        [
            "$$",
            r"\begin{aligned}",
            rf"\text{{Free each month}} &= {inr_tex(flow.income)} - {inr_tex(flow.expenses)}"
            rf" - {inr_tex(flow.emis)} - {inr_tex(flow.premiums)} \\",
            rf"&= {inr_tex(flow.surplus)}",
            r"\end{aligned}",
            "$$",
            ]
        )


def goal_formula(goal: GoalResult) -> str:

    """Return the $$ block that shows each step from today's target to the monthly need and shortfall."""

    period = f"{goal.months}/12"
    saved_today = goal.allocated_today + goal.cash_used

    lines = [
        "$$",
        r"\begin{aligned}",
        rf"\text{{Target in {goal.target_year}}} &= {inr_tex(goal.target_today)} \times (1 + {rate_tex(goal.inflation_pct)})^{{{period}}}"
        rf" = {inr_tex(goal.target_future)} \\",
        rf"\text{{Saved, grown}} &= {inr_tex(saved_today)} \times (1 + {rate_tex(goal.return_pct)})^{{{period}}}"
        rf" = {inr_tex(goal.saved_future)} \\",
        rf"\text{{Gap}} &= {inr_tex(goal.target_future)} - {inr_tex(goal.saved_future)} = {inr_tex(goal.gap)} \\",
        ]

    if goal.gap > 0:
        lines.append(
            rf"\text{{Monthly need}} &= {inr_tex(goal.gap)} \times \frac{{i}}{{(1 + i)^{{{goal.months}}} - 1}},"
            rf"\ i = \frac{{{rate_tex(goal.return_pct)}}}{{12}} = {inr_tex(goal.monthly_need)} \\"
            )

    lines.append(
        rf"\text{{Short by}} &= {inr_tex(goal.monthly_need)} - {inr_tex(goal.monthly_assigned)} = {inr_tex(goal.shortfall)}"
        )

    return "\n".join([*lines, r"\end{aligned}", "$$"])


def goal_line(goal: GoalResult) -> str:

    """Return one plain line with the verdict and key numbers for a goal."""

    verdict = "ON TRACK" if goal.on_track else "NOT on track"

    return (
        f"Goal '{goal.name}' (priority {goal.priority}, by Dec {goal.target_year}, {goal.months} months): {verdict}. "
        f"Target {inr(goal.target_today)} today becomes {inr(goal.target_future)} at {goal.inflation_pct:g}% inflation. "
        f"Saved for it: {inr(goal.allocated_today)} linked + {inr(goal.cash_used)} free cash. "
        f"Needs {inr(goal.monthly_need)}/month at {goal.return_pct:g}% return; "
        f"{inr(goal.monthly_assigned)}/month is available for it; short by {inr(goal.shortfall)}/month."
        )


def goal_progress_report(progress: GoalProgress) -> str:

    """Return the full tool result: a rule for the model, the summary, one line per goal, then every formula."""

    if not progress.goals:
        return "No active goals saved."

    flow = progress.cash_flow

    parts = [
        "These numbers come from exact calculations. Use them as they are and never recalculate them. "
        "If you show a calculation, copy the matching $$ block below exactly.",
        f"Free each month: {inr(flow.surplus)} (income {inr(flow.income)} - expenses {inr(flow.expenses)} "
        f"- loan EMIs {inr(flow.emis)} - insurance premiums {inr(flow.premiums)}). "
        f"Free cash not linked to any goal: {inr(progress.free_cash)}. Goals get money in priority order.",
        *(goal_line(goal) for goal in progress.goals),
        "Free money formula:",
        cash_flow_formula(progress),
        ]

    for goal in progress.goals:
        parts.extend([f"Formula for '{goal.name}':", goal_formula(goal)])

    return "\n\n".join(parts)
