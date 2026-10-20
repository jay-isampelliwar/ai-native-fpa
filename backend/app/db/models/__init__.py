"""Every table model, imported here so callers and Alembic can use app.db.models directly."""

from app.db.models.approvals import ToolApproval
from app.db.models.assets import BankAccount, FixedDeposit, PhysicalAsset, RetirementAccount
from app.db.models.cash_flow import Expense, IncomeSource, Transaction
from app.db.models.coverage import DataCoverage
from app.db.models.conversations import AgentRun, Conversation, Message, ToolCall
from app.db.models.liabilities import CreditCard, Loan
from app.db.models.memory import MemoryEvent, MemoryItem
from app.db.models.outbox import OutboxEvent
from app.db.models.planning import Assumption, Goal, GoalAllocation, TaxProfile
from app.db.models.profile import FamilyMember, User
from app.db.models.protection import InsurancePolicy


__all__ = [
    "AgentRun",
    "Assumption",
    "BankAccount",
    "Conversation",
    "CreditCard",
    "DataCoverage",
    "Expense",
    "FamilyMember",
    "FixedDeposit",
    "Goal",
    "GoalAllocation",
    "IncomeSource",
    "InsurancePolicy",
    "Loan",
    "MemoryEvent",
    "MemoryItem",
    "Message",
    "OutboxEvent",
    "PhysicalAsset",
    "RetirementAccount",
    "TaxProfile",
    "ToolApproval",
    "ToolCall",
    "Transaction",
    "User",
    ]
