"""Database reads and writes for income sources, expenses and transactions."""

from app.db.models import Expense, IncomeSource, Transaction
from app.features.cash_flow.schemas import ExpenseCreate, IncomeSourceCreate, TransactionCreate
from app.features.records.base_repository import BaseUserRecordRepository


class CashFlowRepository(BaseUserRecordRepository):

    """Cash flow queries on top of the shared user record queries."""

    async def add_income_source(self, user_id: int, income: IncomeSourceCreate) -> IncomeSource:

        """Insert an income source for the user."""

        return await self.insert(IncomeSource, user_id, income.model_dump())

    async def add_expense(self, user_id: int, expense: ExpenseCreate) -> Expense:

        """Insert an expense for the user."""

        return await self.insert(Expense, user_id, expense.model_dump())

    async def add_transaction(self, user_id: int, transaction: TransactionCreate) -> Transaction:

        """Insert a one-off transaction for the user."""

        return await self.insert(Transaction, user_id, transaction.model_dump())
