"""The overview tools: net worth, where the money is, this month's cash flow, the health score and what is coming up, each as one card."""

from datetime import date

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage

from app.agent.blocks import (
    asset_split_block,
    cash_flow_block,
    health_block,
    month_summary_block,
    net_worth_block,
    timeline_block,
    )
from app.agent.cards import rupees
from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_session
from app.agent.tools.results import ok, to_message
from app.features.overview.service import OverviewService


@tool
async def get_net_worth(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Add up everything the user owns (bank, deposits, EPF/PPF/NPS, property, stocks and funds) minus everything they owe (loans, card dues) and show net worth as one card. Read-only. Use it for "what is my net worth" or "how much am I worth"."""

    async with tool_session(runtime.context) as session:
        worth = await OverviewService(session).net_worth(runtime.context.user_id)

    data = {
        "net_worth": float(worth.value),
        "assets": float(worth.assets),
        "owed": float(worth.owed),
        "invested": float(worth.invested),
        "cash": float(worth.cash),
        "split": {label: float(value) for label, value in worth.split},
        }

    message = f"Net worth is {rupees(worth.value)}: {rupees(worth.assets)} owned minus {rupees(worth.owed)} owed."

    return to_message(ok(message, data, net_worth_block(worth, date.today())), runtime.tool_call_id)


@tool
async def get_asset_split(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Show how everything the user owns splits by type: property, stocks and funds, EPF/PPF/NPS, bank and deposits, as a ring card. Read-only. Use it for "where is my money" or "how is my money split"."""

    async with tool_session(runtime.context) as session:
        worth = await OverviewService(session).net_worth(runtime.context.user_id)

    data = {"total": float(worth.assets), "split": {label: float(value) for label, value in worth.split}}

    if worth.assets <= 0:
        return to_message(ok("Nothing is saved yet, so there is no split to show.", data), runtime.tool_call_id)

    biggest = worth.split[0]

    message = f"{rupees(worth.assets)} in total; the biggest part is {biggest[0].lower()} at {rupees(biggest[1])}."

    return to_message(ok(message, data, asset_split_block(worth)), runtime.tool_call_id)


@tool
async def get_month_summary(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Show this month's income, spending (expenses, EMIs and premiums) and what is left, as three tiles with a trend when the user has transactions. Read-only. Use it for "how is my month going" or "how much do I save"."""

    today = date.today()

    async with tool_session(runtime.context) as session:
        summary = await OverviewService(session).month_summary(runtime.context.user_id, today)

    data = {
        "income": summary.income,
        "spending": summary.spending,
        "saved": summary.saved,
        "months_of_history": len(summary.history),
        }

    message = f"This month: {rupees(summary.income)} in, {rupees(summary.spending)} out, {rupees(summary.saved)} left."

    return to_message(ok(message, data, month_summary_block(summary, today)), runtime.tool_call_id)


@tool
async def get_cash_flow_history(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Show income against spending for each of the last six months as bars, from the user's saved transactions. Read-only. Use it for "show my cash flow" or "how has my spending changed"."""

    today = date.today()

    async with tool_session(runtime.context) as session:
        summary = await OverviewService(session).month_summary(runtime.context.user_id, today)

    if not summary.history:
        return to_message(ok("No transactions are saved yet, so there is no month-by-month history to show.", {"months": []}), runtime.tool_call_id)

    data = {
        "months": [
            {"month": f"{flow.month:%b %Y}", "income": float(flow.income), "spending": float(flow.spending), "saved": float(flow.saved)}
            for flow in summary.history
            ],
        }

    message = f"Cash flow for the last {len(summary.history)} months is on the card."

    return to_message(ok(message, data, cash_flow_block(summary)), runtime.tool_call_id)


@tool
async def get_financial_health(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """Score the user's financial health out of 100 from four checks: emergency fund, debt to income, savings rate and life cover, as a gauge card. Read-only. Use it for "how healthy are my finances" or "am I doing okay"."""

    today = date.today()

    async with tool_session(runtime.context) as session:
        health = await OverviewService(session).health(runtime.context.user_id, today)

    if health is None:
        return to_message(ok("The score needs the user's monthly income first. Ask for it, then try again.", {"score": None}), runtime.tool_call_id)

    data = {
        "score": health.score,
        "verdict": health.verdict,
        "checks": [{"label": check.label, "value": check.value, "points": round(check.points, 1)} for check in health.checks],
        }

    weakest = min(health.checks, key=lambda check: check.points)

    message = f"Score {health.score} of 100, {health.verdict.lower()}. The weakest check is {weakest.label.lower()}: {weakest.value}."

    return to_message(ok(message, data, health_block(health, today)), runtime.tool_call_id)


@tool
async def get_upcoming_events(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """List what is coming up in the next month: SIP dates, loan EMIs, card due dates, deposits maturing, policy renewals, then goal years, as a timeline card. Read-only. Use it for "what is coming up" or "what do I pay this month"."""

    today = date.today()

    async with tool_session(runtime.context) as session:
        events = await OverviewService(session).upcoming(runtime.context.user_id, today)

    data = {
        "events": [
            {"when": event.when, "date": event.on.isoformat(), "label": event.label, "amount": float(event.value) if event.value is not None else None, "state": event.state}
            for event in events
            ],
        }

    if not events:
        return to_message(ok("Nothing is due in the next month, and there are no active goals.", data), runtime.tool_call_id)

    message = f"{len(events)} things are coming up; the first is {events[0].label} on {events[0].when}."

    return to_message(ok(message, data, timeline_block(events)), runtime.tool_call_id)
