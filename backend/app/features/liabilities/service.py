"""Business rules for adding loans and credit cards."""

from app.db.models import CreditCard, Loan
from app.features.liabilities.repository import LiabilityRepository
from app.features.liabilities.schemas import CreditCardCreate, LoanCreate
from app.features.records.service import BaseRecordService


class LiabilityService(BaseRecordService[LiabilityRepository]):

    """The steps behind the liability tools for one session."""

    repository_class = LiabilityRepository

    async def add_loan(self, user_id: int, loan: LoanCreate) -> Loan:

        """Add the loan. Two loans from the same lender are allowed, since they can be two real loans."""

        record = await self.repo.add_loan(user_id, loan)

        await self.mark_provided(user_id, "loans")

        return record

    async def add_credit_card(self, user_id: int, card: CreditCardCreate) -> CreditCard:

        """Add the card. Two cards from the same bank are allowed."""

        record = await self.repo.add_credit_card(user_id, card)

        await self.mark_provided(user_id, "credit_cards")

        return record
