"""Every ORM table in one import, so metadata is complete before Alembic or a test looks at it.

SQLAlchemy only knows about a table once its module has been imported. Alembic's autogenerate
and the schema comparison test both read ``Base.metadata``, so a model file that nothing
imports is invisible to them and its drift goes unnoticed. Importing them all here makes
that impossible to get wrong.
"""

from app.models.orm.cashflow import ExpenseRecordRow, ExpenseTransactionRow, IncomeRecordRow
from app.models.orm.conversations import ConversationMessageRow, ConversationRow
from app.models.orm.credit import EmiRecordRow, LiabilityRow, SipRecordRow
from app.models.orm.imports import DocumentImportRow, ImportTemplateRow, StagedRowRow
from app.models.orm.investments import (
    DepositRow,
    GoalFundingRow,
    GoalRow,
    HoldingRow,
    InsurancePolicyRow,
    InvestmentTransactionRow,
    RetirementAssetRow,
)
from app.models.orm.system import AuditRecordRow, PendingApprovalRow, UserRow

__all__ = [
    "AuditRecordRow",
    "ConversationMessageRow",
    "ConversationRow",
    "DepositRow",
    "DocumentImportRow",
    "EmiRecordRow",
    "ExpenseRecordRow",
    "ExpenseTransactionRow",
    "GoalFundingRow",
    "ImportTemplateRow",
    "GoalRow",
    "HoldingRow",
    "IncomeRecordRow",
    "InsurancePolicyRow",
    "InvestmentTransactionRow",
    "LiabilityRow",
    "PendingApprovalRow",
    "RetirementAssetRow",
    "SipRecordRow",
    "StagedRowRow",
    "UserRow",
]
