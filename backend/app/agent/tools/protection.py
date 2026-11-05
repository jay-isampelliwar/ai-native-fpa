"""The protection tool: add insurance policies."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage

from app.agent.context import PlannerContext
from app.agent.tools.cash_flow import RUPEES
from app.agent.tools.common import save_record
from app.db.enums import PaymentFrequency, PolicyType
from app.features.protection.schemas import InsurancePolicyCreate
from app.features.protection.service import ProtectionService


@tool
async def add_insurance_policy(
    runtime: ToolRuntime[PlannerContext],
    policy_type: Annotated[PolicyType | None, "The kind of cover."] = None,
    insurer: Annotated[str | None, "The insurance company's name."] = None,
    cover_amount: Annotated[Decimal | None, f"The sum assured or cover. {RUPEES}"] = None,
    premium: Annotated[Decimal | None, f"The premium paid each time. {RUPEES}"] = None,
    premium_frequency: Annotated[PaymentFrequency | None, "How often the premium is paid. Yearly if not said."] = None,
    policy_name: Annotated[str | None, "The plan's name, only if stated."] = None,
    family_member_name: Annotated[str | None, "The saved family member this covers. Leave empty if it covers the user."] = None,
    start_date: Annotated[date | None, "When the policy started, as YYYY-MM-DD, only if stated."] = None,
    renewal_date: Annotated[date | None, "The next renewal date, as YYYY-MM-DD, only if stated."] = None,
    maturity_date: Annotated[date | None, "When the policy matures, as YYYY-MM-DD, only if stated."] = None,
    ) -> ToolMessage:

    """Add one insurance policy, such as term life or health cover. Required: policy type, insurer, cover amount, premium. Its premium is saved here, never also as an expense."""

    return await save_record(
        runtime,
        InsurancePolicyCreate,
        dict(locals()),
        lambda session, user_id, policy: ProtectionService(session).add_policy(user_id, policy),
        "insurance policy",
        )
