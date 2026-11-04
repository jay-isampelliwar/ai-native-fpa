"""Every table model, imported here so callers and Alembic can use app.db.models directly."""

from app.db.models.approvals import ToolApproval
from app.db.models.assets import BankAccount, FixedDeposit, PhysicalAsset, RetirementAccount
from app.db.models.cash_flow import Expense, IncomeSource, Transaction
from app.db.models.coverage import DataCoverage
from app.db.models.investments import FundHolding, Holding, MutualFund, SipPlan, Stock
from app.db.models.conversations import AgentRun, Conversation, Message, RunEventRecord, ToolCall
from app.db.models.liabilities import CreditCard, Loan
from app.db.models.memory import MemoryEvent, MemoryItem
from app.db.models.operations import ToolOperation
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
    "FundHolding",
    "Goal",
    "GoalAllocation",
    "Holding",
    "IncomeSource",
    "InsurancePolicy",
    "Loan",
    "MemoryEvent",
    "MemoryItem",
    "Message",
    "MutualFund",
    "OutboxEvent",
    "PhysicalAsset",
    "RetirementAccount",
    "RunEventRecord",
    "SipPlan",
    "Stock",
    "TaxProfile",
    "ToolApproval",
    "ToolCall",
    "ToolOperation",
    "Transaction",
    "User",
    ]
