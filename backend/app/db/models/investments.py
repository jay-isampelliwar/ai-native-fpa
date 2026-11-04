"""The table models for the shared market tables and the user's own stocks, funds and SIPs."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Identity, Index, Numeric, SmallInteger, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.enums import (
    FundCategory,
    FundOptionType,
    FundPlanType,
    FundSubCategory,
    HoldingAssetClass,
    HoldingAssetType,
    MarketCapType,
    StockExchange,
    StockSector,
    )
from app.db.models.base import MONEY, RATE, UserOwnedMixin, created_at_column, db_enum, updated_at_column
from app.db.session import Base


PRICE = Numeric(14, 4)
UNITS = Numeric(18, 4)


class Stock(Base):

    """One listed share or ETF, shared by every user and filled by the market data scripts."""

    __tablename__ = "stocks"

    __table_args__ = (
        Index("ix_stocks_symbol", "symbol"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    exchange: Mapped[StockExchange | None] = mapped_column(db_enum(StockExchange, "stock_exchange"))
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[StockSector | None] = mapped_column(db_enum(StockSector, "stock_sector"))
    market_cap_type: Mapped[MarketCapType | None] = mapped_column(db_enum(MarketCapType, "market_cap_type"))
    is_etf: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_price: Mapped[Decimal | None] = mapped_column(PRICE)
    price_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class MutualFund(Base):

    """One plan and option of a mutual fund scheme, shared by every user and filled by the market data scripts."""

    __tablename__ = "mutual_funds"

    __table_args__ = (
        Index("ix_mutual_funds_amfi_scheme_code", "amfi_scheme_code"),
        Index("ix_mutual_funds_base_scheme_name", "base_scheme_name"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    amfi_scheme_code: Mapped[str | None] = mapped_column(String(20))
    scheme_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_scheme_name: Mapped[str | None] = mapped_column(String(255))
    amc_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[FundCategory] = mapped_column(db_enum(FundCategory, "fund_category"), nullable=False)
    sub_category: Mapped[FundSubCategory | None] = mapped_column(db_enum(FundSubCategory, "fund_sub_category"))
    plan_type: Mapped[FundPlanType] = mapped_column(db_enum(FundPlanType, "fund_plan_type"), nullable=False)
    option_type: Mapped[FundOptionType] = mapped_column(db_enum(FundOptionType, "fund_option_type"), nullable=False)
    last_nav: Mapped[Decimal | None] = mapped_column(PRICE)
    nav_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class FundHolding(Base):

    """One line of a scheme's latest monthly portfolio, shared by every user."""

    __tablename__ = "fund_holdings"

    __table_args__ = (
        Index("ix_fund_holdings_base_scheme_name", "base_scheme_name"),
        Index("ix_fund_holdings_holding_isin", "holding_isin"),
        Index("ix_fund_holdings_amc_name", "amc_name"),
        )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    amc_name: Mapped[str] = mapped_column(String(100), nullable=False)
    scheme_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_scheme_name: Mapped[str | None] = mapped_column(String(255))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    holding_isin: Mapped[str | None] = mapped_column(String(12))
    holding_name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100))
    sector: Mapped[StockSector | None] = mapped_column(db_enum(StockSector, "stock_sector"))
    asset_class: Mapped[HoldingAssetClass] = mapped_column(
        db_enum(HoldingAssetClass, "holding_asset_class"),
        nullable=False,
        )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    market_value_lakhs: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    weight_pct: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class Holding(UserOwnedMixin, Base):

    """One stock or mutual fund plan the user owns, with its units and value on a given date."""

    __tablename__ = "holdings"

    __table_args__ = (
        Index("ix_holdings_user_id", "user_id"),
        Index("ix_holdings_stock_id", "stock_id"),
        Index("ix_holdings_mutual_fund_id", "mutual_fund_id"),
        )

    asset_type: Mapped[HoldingAssetType] = mapped_column(
        db_enum(HoldingAssetType, "holding_asset_type"),
        nullable=False,
        )
    stock_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("stocks.id"))
    mutual_fund_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("mutual_funds.id"))
    folio_number: Mapped[str | None] = mapped_column(String(30))
    units: Mapped[Decimal] = mapped_column(UNITS, nullable=False)
    avg_buy_price: Mapped[Decimal | None] = mapped_column(PRICE)
    invested_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    current_value: Mapped[Decimal | None] = mapped_column(MONEY)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)


class SipPlan(UserOwnedMixin, Base):

    """One monthly SIP into a holding the user owns."""

    __tablename__ = "sip_plans"

    __table_args__ = (
        Index("ix_sip_plans_user_id", "user_id"),
        Index("ix_sip_plans_holding_id", "holding_id"),
        )

    holding_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("holdings.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sip_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    step_up_rate: Mapped[Decimal | None] = mapped_column(RATE)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())

