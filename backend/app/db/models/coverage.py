"""The table model that tracks, per user and per section, whether data is given, none, declined or pending."""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import CoverageStatus
from app.db.models.base import created_at_column, db_enum, updated_at_column
from app.db.session import Base


def status_column() -> Mapped[CoverageStatus]:

    """A section status column that starts as pending."""

    return mapped_column(
        db_enum(CoverageStatus, "coverage_status"),
        nullable=False,
        server_default=CoverageStatus.pending.value,
        )


class DataCoverage(Base):

    """One row per user with one status column per section of their financial data."""

    __tablename__ = "data_coverage"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    profile: Mapped[CoverageStatus] = status_column()
    family: Mapped[CoverageStatus] = status_column()
    income: Mapped[CoverageStatus] = status_column()
    expenses: Mapped[CoverageStatus] = status_column()
    bank_accounts: Mapped[CoverageStatus] = status_column()
    fixed_deposits: Mapped[CoverageStatus] = status_column()
    retirement_accounts: Mapped[CoverageStatus] = status_column()
    physical_assets: Mapped[CoverageStatus] = status_column()
    loans: Mapped[CoverageStatus] = status_column()
    credit_cards: Mapped[CoverageStatus] = status_column()
    insurance: Mapped[CoverageStatus] = status_column()
    goals: Mapped[CoverageStatus] = status_column()
    tax_profile: Mapped[CoverageStatus] = status_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
