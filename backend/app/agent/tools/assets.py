"""The asset tools: add bank accounts, deposits, retirement accounts and physical assets."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage

from app.agent.context import PlannerContext
from app.agent.tools.cash_flow import RUPEES
from app.agent.tools.common import save_record
from app.db.enums import BankAccountType, DepositType, PhysicalAssetType, RetirementAccountType
from app.features.assets.schemas import (
    BankAccountCreate,
    FixedDepositCreate,
    PhysicalAssetCreate,
    RetirementAccountCreate,
    )
from app.features.assets.service import AssetService


@tool
async def add_bank_account(
    runtime: ToolRuntime[PlannerContext],
    bank_name: Annotated[str | None, "The bank's name, such as HDFC or SBI."] = None,
    account_type: Annotated[BankAccountType | None, "The kind of account."] = None,
    balance: Annotated[Decimal | None, f"The current balance. {RUPEES}"] = None,
    interest_rate: Annotated[Decimal | None, "Yearly interest in percent, only if stated."] = None,
    ) -> ToolMessage:

    """Add one bank account. Required: bank name, account type, balance."""

    return await save_record(
        runtime,
        BankAccountCreate,
        dict(locals()),
        lambda session, user_id, account: AssetService(session).add_bank_account(user_id, account),
        "bank account",
        )


@tool
async def add_fixed_deposit(
    runtime: ToolRuntime[PlannerContext],
    bank_name: Annotated[str | None, "The bank's name."] = None,
    deposit_type: Annotated[DepositType | None, "fd for fixed deposit, rd for recurring deposit."] = None,
    principal: Annotated[Decimal | None, f"The amount deposited. {RUPEES}"] = None,
    interest_rate: Annotated[Decimal | None, "Yearly interest in percent."] = None,
    start_date: Annotated[date | None, "When it was opened, as YYYY-MM-DD."] = None,
    maturity_date: Annotated[date | None, "When it matures, as YYYY-MM-DD."] = None,
    maturity_amount: Annotated[Decimal | None, f"The amount paid at maturity, only if stated. {RUPEES}"] = None,
    ) -> ToolMessage:

    """Add one fixed or recurring deposit. Required: bank name, deposit type, principal, interest rate, start date, maturity date."""

    return await save_record(
        runtime,
        FixedDepositCreate,
        dict(locals()),
        lambda session, user_id, deposit: AssetService(session).add_fixed_deposit(user_id, deposit),
        "fixed deposit",
        )


@tool
async def add_retirement_account(
    runtime: ToolRuntime[PlannerContext],
    account_type: Annotated[RetirementAccountType | None, "epf, ppf, nps or vpf."] = None,
    balance: Annotated[Decimal | None, f"The current balance. {RUPEES}"] = None,
    monthly_contribution: Annotated[Decimal | None, f"What the user puts in each month, only if stated. {RUPEES}"] = None,
    employer_contribution: Annotated[Decimal | None, f"What the employer puts in each month, only if stated. {RUPEES}"] = None,
    interest_rate: Annotated[Decimal | None, "Yearly interest in percent, only if stated."] = None,
    maturity_date: Annotated[date | None, "When it matures, as YYYY-MM-DD, only if stated."] = None,
    ) -> ToolMessage:

    """Add one EPF, PPF, NPS or VPF account. Required: account type, balance."""

    return await save_record(
        runtime,
        RetirementAccountCreate,
        dict(locals()),
        lambda session, user_id, account: AssetService(session).add_retirement_account(user_id, account),
        "retirement account",
        )


@tool
async def add_physical_asset(
    runtime: ToolRuntime[PlannerContext],
    asset_type: Annotated[PhysicalAssetType | None, "real_estate, gold, vehicle or other."] = None,
    name: Annotated[str | None, "A short label, such as 'Pune flat' or 'Gold jewellery'."] = None,
    current_value: Annotated[Decimal | None, f"What it is worth today. {RUPEES}"] = None,
    purchase_value: Annotated[Decimal | None, f"What it cost, only if stated. {RUPEES}"] = None,
    purchase_date: Annotated[date | None, "When it was bought, as YYYY-MM-DD, only if stated."] = None,
    is_self_occupied: Annotated[bool | None, "True if the user lives in this property."] = None,
    ) -> ToolMessage:

    """Add one house, plot, gold, vehicle or other physical asset. Required: asset type, name, current value."""

    return await save_record(
        runtime,
        PhysicalAssetCreate,
        dict(locals()),
        lambda session, user_id, asset: AssetService(session).add_physical_asset(user_id, asset),
        "physical asset",
        )
