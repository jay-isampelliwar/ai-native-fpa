"""The registry of record kinds: for each one, its table model, its checked input and its coverage section."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel

from app.db.models import (
    Assumption,
    BankAccount,
    CreditCard,
    Expense,
    FamilyMember,
    FixedDeposit,
    Goal,
    GoalAllocation,
    IncomeSource,
    InsurancePolicy,
    Loan,
    PhysicalAsset,
    RetirementAccount,
    TaxProfile,
    Transaction,
    )
from app.db.models.base import UserOwnedMixin
from app.features.assets.schemas import (
    BankAccountCreate,
    FixedDepositCreate,
    PhysicalAssetCreate,
    RetirementAccountCreate,
    )
from app.features.cash_flow.schemas import ExpenseCreate, IncomeSourceCreate, TransactionCreate
from app.features.liabilities.schemas import CreditCardCreate, LoanCreate
from app.features.planning.schemas import AssumptionSet, GoalAllocationCreate, GoalCreate, TaxProfileSet
from app.features.profile.schemas import FamilyMemberCreate
from app.features.protection.schemas import InsurancePolicyCreate


class RecordKind(StrEnum):

    """Every kind of saved item the agent can list, change or remove."""

    family = "family"
    income = "income"
    expenses = "expenses"
    transactions = "transactions"
    bank_accounts = "bank_accounts"
    fixed_deposits = "fixed_deposits"
    retirement_accounts = "retirement_accounts"
    physical_assets = "physical_assets"
    loans = "loans"
    credit_cards = "credit_cards"
    insurance = "insurance"
    goals = "goals"
    goal_allocations = "goal_allocations"
    assumptions = "assumptions"
    tax_profile = "tax_profile"


@dataclass(frozen=True)
class KindInfo:

    """What the agent tools need to know about one record kind."""

    model: type[UserOwnedMixin]
    schema: type[BaseModel]
    label: str
    coverage: str | None


KINDS: dict[RecordKind, KindInfo] = {
    RecordKind.family: KindInfo(FamilyMember, FamilyMemberCreate, "family member", "family"),
    RecordKind.income: KindInfo(IncomeSource, IncomeSourceCreate, "income source", "income"),
    RecordKind.expenses: KindInfo(Expense, ExpenseCreate, "expense", "expenses"),
    RecordKind.transactions: KindInfo(Transaction, TransactionCreate, "transaction", None),
    RecordKind.bank_accounts: KindInfo(BankAccount, BankAccountCreate, "bank account", "bank_accounts"),
    RecordKind.fixed_deposits: KindInfo(FixedDeposit, FixedDepositCreate, "fixed deposit", "fixed_deposits"),
    RecordKind.retirement_accounts: KindInfo(
        RetirementAccount,
        RetirementAccountCreate,
        "retirement account",
        "retirement_accounts",
        ),
    RecordKind.physical_assets: KindInfo(PhysicalAsset, PhysicalAssetCreate, "physical asset", "physical_assets"),
    RecordKind.loans: KindInfo(Loan, LoanCreate, "loan", "loans"),
    RecordKind.credit_cards: KindInfo(CreditCard, CreditCardCreate, "credit card", "credit_cards"),
    RecordKind.insurance: KindInfo(InsurancePolicy, InsurancePolicyCreate, "insurance policy", "insurance"),
    RecordKind.goals: KindInfo(Goal, GoalCreate, "goal", "goals"),
    RecordKind.goal_allocations: KindInfo(GoalAllocation, GoalAllocationCreate, "goal allocation", None),
    RecordKind.assumptions: KindInfo(Assumption, AssumptionSet, "assumption", None),
    RecordKind.tax_profile: KindInfo(TaxProfile, TaxProfileSet, "tax profile", "tax_profile"),
    }

COVERAGE_MODELS: dict[str, type[UserOwnedMixin]] = {
    info.coverage: info.model for info in KINDS.values() if info.coverage is not None
    }
