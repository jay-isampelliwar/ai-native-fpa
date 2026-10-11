"""Database reads and writes for income sources, expenses and transactions."""

from app.db.models import Expense, IncomeSource, Transaction
from app.features.cash_flow.schemas import ExpenseCreate, IncomeSourceCreate, TransactionCreate
from app.features.records.base_repository import BaseUserRecordRepository


class CashFlowRepository(BaseUserRecordRepository):

    """Cash flow queries on top of the shared user record queries."""

    async def find_income_source(self, user_id: int, income: IncomeSourceCreate) -> IncomeSource | None:

        """Return the user's income with the same type and name."""

        return await self.find_match(IncomeSource, user_id, {"source_type": income.source_type, "name": income.name})

    async def add_income_source(self, user_id: int, income: IncomeSourceCreate) -> IncomeSource:

        """Insert an income source for the user."""

        return await self.insert(IncomeSource, user_id, income.model_dump())

    async def find_expense(self, user_id: int, expense: ExpenseCreate) -> Expense | None:

        """Return the user's expense with the same category and name."""

        return await self.find_match(Expense, user_id, {"category": expense.category, "name": expense.name})

    async def add_expense(self, user_id: int, expense: ExpenseCreate) -> Expense:

        """Insert an expense for the user."""

        return await self.insert(Expense, user_id, expense.model_dump())

    async def add_transaction(self, user_id: int, transaction: TransactionCreate) -> Transaction:

        """Insert a one-off transaction for the user."""

        return await self.insert(Transaction, user_id, transaction.model_dump())
