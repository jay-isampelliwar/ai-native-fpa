"""The table models for bank accounts, deposits, retirement accounts and physical assets."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Index, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import BankAccountType, DepositType, PhysicalAssetType, RetirementAccountType
from app.db.models.base import MONEY, RATE, UserOwnedMixin, db_enum
from app.db.session import Base


class BankAccount(UserOwnedMixin, Base):

    """One bank account and its balance on a given date."""

    __tablename__ = "bank_accounts"

    __table_args__ = (
        Index("ix_bank_accounts_user_id", "user_id"),
        )

    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[BankAccountType] = mapped_column(db_enum(BankAccountType, "bank_account_type"), nullable=False)
    balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    interest_rate: Mapped[Decimal | None] = mapped_column(RATE)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)


class FixedDeposit(UserOwnedMixin, Base):

    """One fixed or recurring deposit with its rate and maturity."""

    __tablename__ = "fixed_deposits"

    __table_args__ = (
        Index("ix_fixed_deposits_user_id", "user_id"),
        )

    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    deposit_type: Mapped[DepositType] = mapped_column(db_enum(DepositType, "deposit_type"), nullable=False)
    principal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_amount: Mapped[Decimal | None] = mapped_column(MONEY)


class RetirementAccount(UserOwnedMixin, Base):

    """One EPF, PPF, NPS or VPF account and its balance on a given date."""

    __tablename__ = "retirement_accounts"

    __table_args__ = (
        Index("ix_retirement_accounts_user_id", "user_id"),
        )

    account_type: Mapped[RetirementAccountType] = mapped_column(
        db_enum(RetirementAccountType, "retirement_account_type"),
        nullable=False,
        )
    balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    monthly_contribution: Mapped[Decimal | None] = mapped_column(MONEY)
    employer_contribution: Mapped[Decimal | None] = mapped_column(MONEY)
    interest_rate: Mapped[Decimal | None] = mapped_column(RATE)
    maturity_date: Mapped[date | None] = mapped_column(Date)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)


class PhysicalAsset(UserOwnedMixin, Base):

    """One house, plot, gold, vehicle or other physical thing of value."""

    __tablename__ = "physical_assets"

    __table_args__ = (
        Index("ix_physical_assets_user_id", "user_id"),
        )

    asset_type: Mapped[PhysicalAssetType] = mapped_column(db_enum(PhysicalAssetType, "physical_asset_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purchase_value: Mapped[Decimal | None] = mapped_column(MONEY)
    current_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    is_self_occupied: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
