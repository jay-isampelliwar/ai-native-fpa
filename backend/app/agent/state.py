"""What one chat turn carries through the graph."""

from typing import NotRequired

from langgraph.graph import MessagesState

from app.agent.user_data import (
    Deposit,
    Emi,
    Expense,
    Goal,
    Income,
    InsurancePolicy,
    Loan,
    MutualFund,
    RetirementAsset,
    Sip,
    Spend,
    Stock,
    UserProfile,
)


class PlannerState(MessagesState):

    """One chat turn: the thread's messages, who is asking, and every record loaded about their money."""

    user_id: int
    conversation_id: str

    profile: NotRequired[UserProfile]

    income: NotRequired[list[Income]]
    expenses: NotRequired[list[Expense]]
    loans: NotRequired[list[Loan]]
    emis: NotRequired[list[Emi]]
    sips: NotRequired[list[Sip]]

    mutual_funds: NotRequired[list[MutualFund]]
    stocks: NotRequired[list[Stock]]
    deposits: NotRequired[list[Deposit]]
    retirement_assets: NotRequired[list[RetirementAsset]]
    insurance_policies: NotRequired[list[InsurancePolicy]]

    goals: NotRequired[list[Goal]]
    recent_spends: NotRequired[list[Spend]]

    conversation_summary: NotRequired[str]
