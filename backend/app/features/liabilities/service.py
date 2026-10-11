"""Business rules for adding loans and credit cards."""

from app.db.models import CreditCard, Loan
from app.features.liabilities.repository import LiabilityRepository
from app.features.liabilities.schemas import CreditCardCreate, LoanCreate
from app.features.records.exceptions import RecordExists
from app.features.records.service import BaseRecordService


class LiabilityService(BaseRecordService[LiabilityRepository]):

    """The steps behind the liability tools for one session."""

    repository_class = LiabilityRepository

    async def add_loan(self, user_id: int, loan: LoanCreate) -> Loan:

        """Add the loan unless one of the same type from the same lender is already saved."""

        existing = await self.repo.find_loan(user_id, loan)

        if existing is not None:
            raise RecordExists("loan", existing.id)

        record = await self.repo.add_loan(user_id, loan)

        await self.mark_provided(user_id, "loans")

        await self.session.commit()

        return record

    async def add_credit_card(self, user_id: int, card: CreditCardCreate) -> CreditCard:

        """Add the card unless one from the same bank is already saved."""

        existing = await self.repo.find_credit_card(user_id, card)

        if existing is not None:
            raise RecordExists("credit card", existing.id)

        record = await self.repo.add_credit_card(user_id, card)

        await self.mark_provided(user_id, "credit_cards")

        await self.session.commit()

        return record
