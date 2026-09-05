"""Borrowing and standing instructions: the outflows that are not ordinary expenses.

The distinction this module encodes is the one most advice turns on. An EMI is
contractual - missing it has consequences beyond the money - while an SIP is voluntary and
can be paused this month and resumed next. A cash flow calculator that treated both as
"outflow" would report the same surplus for a household that can breathe and one that
cannot.

``LiabilityRow`` and ``EmiRecordRow`` are separate because they answer different questions.
The liability holds the debt: what is outstanding, at what rate, for how long. The EMI
holds the payment that services it. A user can restructure a loan, changing the EMI while
the liability persists, and the repayment strategies in Phase 2b need both sides.

``SipRecordRow`` is a standing instruction, not an asset. The units it buys live in
``holdings`` and the debits it produces live in ``investment_transactions``; this row is
only the arrangement. Modelling an SIP as an asset class is the mistake the implementation
guide calls out, and it would make every allocation figure wrong by double counting.

``linked_goal_id`` is intentionally not a foreign key. An SIP frequently exists before the
goal it later funds, and requiring the goal first would force users to invent one; the
funding relationship proper lives in ``goal_fundings``.
"""

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, Rate, RecordId, TimestampMixin
from app.models.finance import Frequency, SipStatus
from app.models.orm.enums import FREQUENCY, SIP_STATUS


class LiabilityRow(Base, TimestampMixin):

    """A debt the user owes, holding what is outstanding rather than what is paid each month."""

    __tablename__ = "liabilities"

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    lender: Mapped[str] = mapped_column(Text, nullable=False, default="")
    principal_outstanding: Mapped[Money]
    interest_rate_percent: Mapped[Rate]
    tenure_months: Mapped[int] = mapped_column(Integer, nullable=False)
    opened_on: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("principal_outstanding >= 0", name="ck_liabilities_principal_non_negative"),
        CheckConstraint("tenure_months > 0", name="ck_liabilities_tenure_positive"),
    )


class EmiRecordRow(Base, TimestampMixin):

    """The contractual payment servicing a liability, which cannot be paused the way an SIP can."""

    __tablename__ = "emi_records"

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    liability_id: Mapped[str] = mapped_column(
        ForeignKey("liabilities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Money]
    frequency: Mapped[Frequency] = mapped_column(FREQUENCY, nullable=False, default=Frequency.MONTHLY)
    interest_rate_percent: Mapped[Rate]
    remaining_months: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_emi_amount_positive"),
        CheckConstraint("remaining_months >= 0", name="ck_emi_remaining_non_negative"),
    )


class SipRecordRow(Base, TimestampMixin):

    """A recurring instruction into a scheme, discretionary and therefore adjustable with approval."""

    __tablename__ = "sip_records"

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    scheme_name: Mapped[str] = mapped_column(Text, nullable=False)
    folio_id: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Money]
    frequency: Mapped[Frequency] = mapped_column(FREQUENCY, nullable=False, default=Frequency.MONTHLY)
    next_debit_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[SipStatus] = mapped_column(SIP_STATUS, nullable=False, default=SipStatus.ACTIVE)
    linked_goal_id: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (CheckConstraint("amount > 0", name="ck_sip_amount_positive"),)
