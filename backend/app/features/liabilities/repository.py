"""Database reads and writes for loans and credit cards."""

from app.db.models import CreditCard, Loan
from app.features.liabilities.schemas import CreditCardCreate, LoanCreate
from app.features.records.base_repository import BaseUserRecordRepository


class LiabilityRepository(BaseUserRecordRepository):

    """Liability queries on top of the shared user record queries."""

    async def add_loan(self, user_id: int, loan: LoanCreate) -> Loan:

        """Insert a loan for the user."""

        return await self.insert(Loan, user_id, loan.model_dump())

    async def add_credit_card(self, user_id: int, card: CreditCardCreate) -> CreditCard:

        """Insert a credit card for the user."""

        return await self.insert(CreditCard, user_id, card.model_dump())
