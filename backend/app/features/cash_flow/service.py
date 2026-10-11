"""Business rules for adding income sources, expenses and transactions."""

from app.db.models import Expense, IncomeSource, Transaction
from app.features.cash_flow.repository import CashFlowRepository
from app.features.cash_flow.schemas import ExpenseCreate, IncomeSourceCreate, TransactionCreate
from app.features.records.exceptions import RecordExists
from app.features.records.service import BaseRecordService


class CashFlowService(BaseRecordService[CashFlowRepository]):

    """The steps behind the cash flow tools for one session."""

    repository_class = CashFlowRepository

    async def add_income_source(self, user_id: int, income: IncomeSourceCreate) -> IncomeSource:

        """Add the income unless one with the same type and name is already saved."""

        existing = await self.repo.find_income_source(user_id, income)

        if existing is not None:
            raise RecordExists("income source", existing.id)

        record = await self.repo.add_income_source(user_id, income)

        await self.mark_provided(user_id, "income")

        await self.session.commit()

        return record

    async def add_expense(self, user_id: int, expense: ExpenseCreate) -> Expense:

        """Add the expense unless one with the same category and name is already saved."""

        existing = await self.repo.find_expense(user_id, expense)

        if existing is not None:
            raise RecordExists("expense", existing.id)

        record = await self.repo.add_expense(user_id, expense)

        await self.mark_provided(user_id, "expenses")

        await self.session.commit()

        return record

    async def add_transaction(self, user_id: int, transaction: TransactionCreate) -> Transaction:

        """Add the transaction; repeats are allowed, since two equal amounts can be two real events."""

        record = await self.repo.add_transaction(user_id, transaction)

        await self.session.commit()

        return record
