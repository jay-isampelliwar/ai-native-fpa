"""The table models for loans and credit cards, the money the user owes."""

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import LoanType
from app.db.models.base import MONEY, RATE, UserOwnedMixin, db_enum
from app.db.session import Base


class Loan(UserOwnedMixin, Base):

    """One loan with its amount, outstanding balance, rate, EMI and term."""

    __tablename__ = "loans"

    __table_args__ = (
        Index("ix_loans_user_id", "user_id"),
        )

    loan_type: Mapped[LoanType] = mapped_column(db_enum(LoanType, "loan_type"), nullable=False)
    lender: Mapped[str] = mapped_column(String(100), nullable=False)
    principal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    outstanding: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    emi: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    physical_asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("physical_assets.id"))


class CreditCard(UserOwnedMixin, Base):

    """One credit card with its limit and the amount owed on a given date."""

    __tablename__ = "credit_cards"

    __table_args__ = (
        Index("ix_credit_cards_user_id", "user_id"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_credit_cards_due_day"),
        )

    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    credit_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    outstanding: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    due_day: Mapped[int | None] = mapped_column(SmallInteger)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
