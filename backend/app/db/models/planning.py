"""The table models for goals, goal allocations, planning assumptions and the yearly tax profile."""

from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import AssumptionKey, GoalAssetTable, GoalStatus, GoalType, TaxRegime
from app.db.models.base import MONEY, RATE, UserOwnedMixin, db_enum
from app.db.session import Base


class Goal(UserOwnedMixin, Base):

    """One financial goal with its target amount and year."""

    __tablename__ = "goals"

    __table_args__ = (
        Index("ix_goals_user_id", "user_id"),
        )

    goal_type: Mapped[GoalType] = mapped_column(db_enum(GoalType, "goal_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    target_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    inflation_rate: Mapped[Decimal | None] = mapped_column(RATE)
    family_member_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("family_members.id"))
    status: Mapped[GoalStatus] = mapped_column(
        db_enum(GoalStatus, "goal_status"),
        nullable=False,
        server_default=GoalStatus.active.value,
        )


class GoalAllocation(UserOwnedMixin, Base):

    """The share of one asset set aside for one goal, as a percentage."""

    __tablename__ = "goal_allocations"

    __table_args__ = (
        UniqueConstraint("goal_id", "asset_table", "asset_id", name="uq_goal_allocations_goal_asset"),
        CheckConstraint("allocation_pct > 0 AND allocation_pct <= 100", name="ck_goal_allocations_allocation_pct"),
        Index("ix_goal_allocations_asset", "asset_table", "asset_id"),
        Index("ix_goal_allocations_user_id", "user_id"),
        )

    goal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("goals.id"), nullable=False)
    asset_table: Mapped[GoalAssetTable] = mapped_column(db_enum(GoalAssetTable, "goal_asset_table"), nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocation_pct: Mapped[Decimal] = mapped_column(RATE, nullable=False)


class Assumption(UserOwnedMixin, Base):

    """One planning rate the user chose, such as inflation or equity return."""

    __tablename__ = "assumptions"

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_assumptions_user_key"),
        )

    key: Mapped[AssumptionKey] = mapped_column(db_enum(AssumptionKey, "assumption_key"), nullable=False)
    value: Mapped[Decimal] = mapped_column(RATE, nullable=False)


class TaxProfile(UserOwnedMixin, Base):

    """The user's tax regime and deductions used for one financial year."""

    __tablename__ = "tax_profile"

    __table_args__ = (
        UniqueConstraint("user_id", "financial_year", name="uq_tax_profile_user_year"),
        )

    financial_year: Mapped[str] = mapped_column(String(9), nullable=False)
    regime: Mapped[TaxRegime] = mapped_column(db_enum(TaxRegime, "tax_regime"), nullable=False)
    sec_80c_used: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    sec_80d_used: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
    hra_claimed: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="0")
