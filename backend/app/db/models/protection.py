"""The table model for insurance policies: term, health, life and other covers."""

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import PaymentFrequency, PolicyType
from app.db.models.base import MONEY, UserOwnedMixin, db_enum
from app.db.session import Base


class InsurancePolicy(UserOwnedMixin, Base):

    """One insurance policy with its cover, premium and the family member it covers."""

    __tablename__ = "insurance_policies"

    __table_args__ = (
        Index("ix_insurance_policies_user_id", "user_id"),
        )

    policy_type: Mapped[PolicyType] = mapped_column(db_enum(PolicyType, "policy_type"), nullable=False)
    insurer: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_name: Mapped[str | None] = mapped_column(String(255))
    cover_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    premium: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    premium_frequency: Mapped[PaymentFrequency] = mapped_column(
        db_enum(PaymentFrequency, "payment_frequency"),
        nullable=False,
        server_default=PaymentFrequency.yearly.value,
        )
    family_member_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("family_members.id"))
    start_date: Mapped[date | None] = mapped_column(Date)
    renewal_date: Mapped[date | None] = mapped_column(Date)
    maturity_date: Mapped[date | None] = mapped_column(Date)
