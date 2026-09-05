"""Goals, and the assets that fund them: deposits, holdings, retirement schemes and cover.

The modelling rule running through this module is that a goal never holds money. ``GoalRow``
records what is wanted and by when; ``GoalFundingRow`` records which assets are earmarked
for it and in what proportion. A goal that stored a balance would be a second copy of a
number the asset already owns, and the two would disagree the first time a market moved.

``GoalFundingRow`` points at an asset by table name and id rather than through four nullable
foreign keys. That trades referential integrity for a shape that does not need a schema
change every time a new fundable asset type appears, and the allowed tables are constrained
so the looseness is bounded.

``HoldingRow`` and ``InvestmentTransactionRow`` are the same distinction the doc draws
between a holding and a transaction. The holding is the running position - units and average
cost as of a date. The transactions are what happened to produce it. Only one of them can be
reconciled against a broker statement, and it is not the holding.

``last_price`` and ``current_value`` are what a statement stated when it was exported, dated by
``as_of``. They are a record of what the document said, not a live valuation - nothing refreshes them,
and a caller wanting today's value needs a price feed. ``identifier_type`` says what the row was
matched on, because two of the three real statement formats carry no ISIN and a holding keyed on a
scheme name is weaker evidence than one keyed on an ISIN.

``DepositRow`` carries both FD and RD with a check constraint deciding which columns are
required. They differ by exactly one field - a lump sum against a monthly contribution - and
two tables would duplicate the maturity logic they share.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, Rate, RecordId, TimestampMixin, Units
from app.models.finance import DepositKind, Frequency, HoldingKind
from app.models.orm.enums import DEPOSIT_KIND, FREQUENCY, HOLDING_KIND

FUNDABLE_TABLES = "('holdings','deposits','sip_records','retirement_assets')"


class GoalRow(Base, TimestampMixin):

    """Something the user is saving towards, holding the target rather than the money."""

    __tablename__ = "goals"

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="custom")
    target_amount: Mapped[Money]
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    inflation_percent: Mapped[Rate]
    archived_at: Mapped[datetime | None] = mapped_column()
    created_by_approval: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("target_amount > 0", name="ck_goals_target_positive"),
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_goals_priority_range"),
    )


class GoalFundingRow(Base):

    """Links a goal to an asset earmarked for it, without ever copying that asset's balance."""

    __tablename__ = "goal_fundings"
    __table_args__ = (
        UniqueConstraint("goal_id", "asset_table", "asset_id", name="uq_goal_funding_asset"),
        CheckConstraint(f"asset_table IN {FUNDABLE_TABLES}", name="ck_goal_funding_asset_table"),
        CheckConstraint("allocation_pct > 0 AND allocation_pct <= 100", name="ck_goal_funding_allocation"),
    )

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    asset_table: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[str] = mapped_column(Text, nullable=False)
    allocation_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("100.00"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class DepositRow(Base):

    """A term or recurring deposit, sharing maturity behaviour and differing by one column."""

    __tablename__ = "deposits"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'fd' AND principal IS NOT NULL) OR (kind = 'rd' AND monthly_contribution IS NOT NULL)",
            name="ck_deposits_kind_columns",
        ),
        Index("ix_deposits_user_maturity", "user_id", "matures_on"),
    )

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    kind: Mapped[DepositKind] = mapped_column(DEPOSIT_KIND, nullable=False)
    institution: Mapped[str] = mapped_column(Text, nullable=False)
    principal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    monthly_contribution: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    interest_rate_percent: Mapped[Rate]
    compounding: Mapped[str] = mapped_column(Text, nullable=False, default="quarterly")
    opened_on: Mapped[date] = mapped_column(Date, nullable=False)
    matures_on: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class HoldingRow(Base, TimestampMixin):

    """The running position in one instrument, carrying units and cost but never a current price."""

    __tablename__ = "holdings"

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    kind: Mapped[HoldingKind] = mapped_column(HOLDING_KIND, nullable=False)
    instrument_name: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str | None] = mapped_column(Text)
    scheme_code: Mapped[str | None] = mapped_column(Text)
    folio_id: Mapped[str | None] = mapped_column(Text)
    units: Mapped[Units]
    average_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    account_label: Mapped[str | None] = mapped_column(Text)
    asset_type: Mapped[str | None] = mapped_column(Text)
    identifier_type: Mapped[str] = mapped_column(Text, nullable=False, default="symbol")
    invested_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    source: Mapped[str | None] = mapped_column(Text)
    import_batch_id: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("units >= 0", name="ck_holdings_units_non_negative"),
        CheckConstraint("average_cost >= 0", name="ck_holdings_cost_non_negative"),
    )


class InvestmentTransactionRow(Base):

    """One thing that happened to a holding, which is what reconciles against a broker statement."""

    __tablename__ = "investment_transactions"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('buy','sell','dividend','redemption','bonus','split')",
            name="ck_investment_transaction_kind",
        ),
        Index("ix_investment_transactions_user_date", "user_id", "occurred_on"),
        Index("ix_investment_transactions_holding_date", "holding_id", "occurred_on"),
    )

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    holding_id: Mapped[str | None] = mapped_column(ForeignKey("holdings.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    units: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    price_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    amount: Mapped[Money]
    sip_id: Mapped[str | None] = mapped_column(ForeignKey("sip_records.id", ondelete="SET NULL"))
    import_batch_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class RetirementAssetRow(Base):

    """An accumulation scheme, kept apart from ordinary holdings because withdrawal rules differ."""

    __tablename__ = "retirement_assets"
    __table_args__ = (
        CheckConstraint(
            "scheme IN ('epf','ppf','nps','pension','annuity')",
            name="ck_retirement_scheme",
        ),
        CheckConstraint("balance >= 0", name="ck_retirement_balance_non_negative"),
    )

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    scheme: Mapped[str] = mapped_column(Text, nullable=False)
    account_reference: Mapped[str | None] = mapped_column(Text)
    balance: Mapped[Money]
    monthly_contribution: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    employer_contribution: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    interest_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class InsurancePolicyRow(Base):

    """Protection cover and its renewal calendar, tracked as information rather than as an asset."""

    __tablename__ = "insurance_policies"
    __table_args__ = (
        CheckConstraint(
            "policy_kind IN ('term','health','motor','home','endowment','ulip')",
            name="ck_insurance_policy_kind",
        ),
        Index("ix_insurance_user_renewal", "user_id", "renews_on"),
    )

    id: Mapped[RecordId]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    insurer: Mapped[str] = mapped_column(Text, nullable=False)
    policy_kind: Mapped[str] = mapped_column(Text, nullable=False)
    policy_reference: Mapped[str | None] = mapped_column(Text)
    cover_amount: Mapped[Money]
    premium_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    premium_frequency: Mapped[Frequency] = mapped_column(FREQUENCY, nullable=False, default=Frequency.ANNUAL)
    renews_on: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
