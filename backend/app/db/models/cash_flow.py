"""The table models for regular income, regular expenses and one-off transactions."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Index, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import (
    ExpenseCategory,
    IncomeSourceType,
    PaymentFrequency,
    TransactionCategory,
    TransactionDirection,
    )
from app.db.models.base import MONEY, RATE, UserOwnedMixin, db_enum
from app.db.session import Base


class IncomeSource(UserOwnedMixin, Base):

    """One regular income, such as a salary or rent received."""

    __tablename__ = "income_sources"

    __table_args__ = (
        Index("ix_income_sources_user_id", "user_id"),
        )

    source_type: Mapped[IncomeSourceType] = mapped_column(db_enum(IncomeSourceType, "income_source_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    frequency: Mapped[PaymentFrequency] = mapped_column(
        db_enum(PaymentFrequency, "payment_frequency"),
        nullable=False,
        server_default=PaymentFrequency.monthly.value,
        )
    yearly_growth_rate: Mapped[Decimal | None] = mapped_column(RATE)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class Expense(UserOwnedMixin, Base):

    """One regular expense, such as rent, groceries or school fees."""

    __tablename__ = "expenses"

    __table_args__ = (
        Index("ix_expenses_user_id", "user_id"),
        )

    category: Mapped[ExpenseCategory] = mapped_column(db_enum(ExpenseCategory, "expense_category"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    frequency: Mapped[PaymentFrequency] = mapped_column(
        db_enum(PaymentFrequency, "payment_frequency"),
        nullable=False,
        server_default=PaymentFrequency.monthly.value,
        )
    is_essential: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    end_date: Mapped[date | None] = mapped_column(Date)


class Transaction(UserOwnedMixin, Base):

    """One one-off amount that came in or went out, such as a bonus or a repair."""

    __tablename__ = "transactions"

    __table_args__ = (
        Index("ix_transactions_user_id", "user_id"),
        )

    direction: Mapped[TransactionDirection] = mapped_column(
        db_enum(TransactionDirection, "transaction_direction"),
        nullable=False,
        )
    category: Mapped[TransactionCategory] = mapped_column(
        db_enum(TransactionCategory, "transaction_category"),
        nullable=False,
        )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
