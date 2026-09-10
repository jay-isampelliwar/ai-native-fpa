
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.finance import DepositKind, Frequency, SipStatus


class Income(BaseModel):

    """One earning arrangement at the cadence it actually arrives, such as a salary or rent."""

    id: str
    label: str
    amount: Decimal
    frequency: Frequency = Frequency.MONTHLY
    source: str = "salary"


class Expense(BaseModel):

    """One recurring cost the user has committed to, separate from the spends that realise it."""

    id: str
    label: str
    amount: Decimal
    frequency: Frequency = Frequency.MONTHLY
    category: str = "general"


class Loan(BaseModel):

    """One debt with what is still owed on it, which is not the same as what is paid each month."""

    id: str
    label: str
    lender: str = ""
    principal_outstanding: Decimal
    interest_rate_percent: Decimal
    tenure_months: int


class Emi(BaseModel):

    """One contractual instalment servicing a loan, which cannot be paused the way an SIP can."""

    id: str
    label: str
    amount: Decimal
    frequency: Frequency = Frequency.MONTHLY
    interest_rate_percent: Decimal
    remaining_months: int
    loan_id: str | None = None


class Sip(BaseModel):

    """One standing instruction into a scheme, which is an arrangement rather than an asset."""

    id: str
    scheme_name: str
    amount: Decimal
    frequency: Frequency = Frequency.MONTHLY
    status: SipStatus = SipStatus.ACTIVE
    folio_id: str | None = None
    next_debit_on: date | None = None
    goal_id: str | None = None


class MutualFund(BaseModel):

    """One fund position, carrying units and cost paid beside whatever the last statement valued it at."""

    id: str
    scheme_name: str
    units: Decimal
    average_cost: Decimal
    invested_value: Decimal | None = None
    current_value: Decimal | None = None
    as_of: date
    folio_id: str | None = None
    isin: str | None = None
    scheme_code: str | None = None


class Stock(BaseModel):

    """One share position, carrying units and cost paid beside the price the last statement stated."""

    id: str
    instrument_name: str
    units: Decimal
    average_cost: Decimal
    last_price: Decimal | None = None
    invested_value: Decimal | None = None
    current_value: Decimal | None = None
    as_of: date
    isin: str | None = None
    account_label: str | None = None


class Deposit(BaseModel):

    """One term or recurring deposit, differing by whether a lump sum or a monthly amount was put in."""

    id: str
    kind: DepositKind
    institution: str
    interest_rate_percent: Decimal
    opened_on: date
    matures_on: date
    principal: Decimal | None = None
    monthly_contribution: Decimal | None = None
    compounding: str = "quarterly"


class RetirementAsset(BaseModel):

    """One accumulation scheme such as EPF or NPS, kept apart because withdrawal rules differ."""

    id: str
    scheme: str
    balance: Decimal
    monthly_contribution: Decimal = Decimal("0")
    employer_contribution: Decimal = Decimal("0")
    as_of: date
    interest_rate_percent: Decimal | None = None
    account_reference: str | None = None


class InsurancePolicy(BaseModel):

    """One cover and its renewal date, tracked as protection rather than counted as an asset."""

    id: str
    insurer: str
    policy_kind: str
    cover_amount: Decimal
    premium_amount: Decimal
    premium_frequency: Frequency = Frequency.ANNUAL
    renews_on: date | None = None
    policy_reference: str | None = None


class Goal(BaseModel):

    """One thing being saved towards, with the funding attached to it valued when it was read."""

    id: str
    label: str
    kind: str = "custom"
    target_amount: Decimal
    target_date: date
    priority: int = 3
    inflation_percent: Decimal = Decimal("6")
    funded_corpus: Decimal = Decimal("0")
    monthly_contribution: Decimal = Decimal("0")


class Spend(BaseModel):

    """One dated transaction, the unit a spending question reads rather than a budgeted amount."""

    id: str
    occurred_on: date
    amount: Decimal
    category: str
    merchant: str = ""
    description: str = ""


class UserProfile(BaseModel):

    """Who the turn is for and the locale every amount and date should be read in."""

    user_id: int
    name: str = ""
    email: str = ""
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"
