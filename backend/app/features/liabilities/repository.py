"""Database reads and writes for loans and credit cards."""

from app.db.models import CreditCard, Loan
from app.features.liabilities.schemas import CreditCardCreate, LoanCreate
from app.features.records.base_repository import BaseUserRecordRepository


class LiabilityRepository(BaseUserRecordRepository):

    """Liability queries on top of the shared user record queries."""

    async def find_loan(self, user_id: int, loan: LoanCreate) -> Loan | None:

        """Return the user's loan of the same type from the same lender."""

        return await self.find_match(Loan, user_id, {"loan_type": loan.loan_type, "lender": loan.lender})

    async def add_loan(self, user_id: int, loan: LoanCreate) -> Loan:

        """Insert a loan for the user."""

        return await self.insert(Loan, user_id, loan.model_dump())

    async def find_credit_card(self, user_id: int, card: CreditCardCreate) -> CreditCard | None:

        """Return the user's credit card from the same bank."""

        return await self.find_match(CreditCard, user_id, {"bank_name": card.bank_name})

    async def add_credit_card(self, user_id: int, card: CreditCardCreate) -> CreditCard:

        """Insert a credit card for the user."""

        return await self.insert(CreditCard, user_id, card.model_dump())
