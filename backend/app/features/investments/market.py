"""Read-only questions about the shared market data: find stocks and funds, a fund's portfolio, who holds a stock, and a user's sector mix."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import FundCategory, HoldingAssetClass, HoldingAssetType
from app.db.models import FundHolding, Holding, MutualFund, Stock
from app.features.records.exceptions import RecordNotFound


SEARCH_LIMIT = 8
MIN_SYMBOL_PREFIX = 3
MAX_SEARCH_LIMIT = 20
TOP_HOLDINGS = 10
MAX_TOP_HOLDINGS = 50
TOP_FUNDS_HOLDING = 10
MIN_COMPARE = 2
MAX_COMPARE = 4
OTHER_SECTOR = "other"
NOT_BROKEN_DOWN = "not_broken_down"
HUNDRED = Decimal(100)


class InstrumentKind(StrEnum):

    """Which market list a search looks in."""

    any = "any"
    stock = "stock"
    etf = "etf"
    fund = "fund"


@dataclass(frozen=True)
class SearchFilters:

    """Optional narrowing for a search, each one ignored when empty."""

    sector: str | None = None
    market_cap: str | None = None
    category: str | None = None
    sub_category: str | None = None
    amc: str | None = None


def money(value: Decimal | None) -> float | None:

    """A rupee amount rounded to paise, for a tool result."""

    return None if value is None else float(round(value, 2))


def percent(value: Decimal | float) -> float:

    """A percentage rounded to two decimals, for a tool result."""

    return float(round(Decimal(str(value)), 2))


def words_of(query: str) -> list[str]:

    """The search words, lowercased, without very short ones."""

    return [word for word in query.lower().replace("-", " ").split() if len(word) > 1]


def name_matches(
    query: Select,
    column: Any,
    words: list[str],
    ) -> Select:

    """Keep rows whose name has every search word in it."""

    for word in words:
        query = query.where(func.lower(column).contains(word))

    return query


def stock_item(stock: Stock) -> dict[str, Any]:

    """One stock or ETF as a search or detail result."""

    return {
        "kind": "etf" if stock.is_etf else "stock",
        "isin": stock.isin,
        "symbol": stock.symbol,
        "name": stock.company_name,
        "exchange": stock.exchange,
        "sector": stock.sector,
        "market_cap": stock.market_cap_type,
        "last_price": money(stock.last_price),
        "price_date": stock.price_date,
        }


def plan_item(fund: MutualFund) -> dict[str, Any]:

    """One fund plan as a search or detail result."""

    return {
        "isin": fund.isin,
        "plan": fund.plan_type,
        "option": fund.option_type,
        "scheme_name": fund.scheme_name,
        "nav": money(fund.last_nav),
        "nav_date": fund.nav_date,
        }


def sector_split(rows: Sequence[FundHolding]) -> list[dict[str, Any]]:

    """The equity part of a portfolio added up by sector, largest first."""

    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)

    for row in rows:

        if row.asset_class != HoldingAssetClass.equity:
            continue

        sector = row.sector.value if row.sector else OTHER_SECTOR
        totals[sector] += row.weight_pct
        counts[sector] += 1

    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)

    return [{"sector": sector, "weight_pct": percent(weight), "holdings": counts[sector]} for sector, weight in ordered]


def asset_split(rows: Sequence[FundHolding]) -> dict[str, float]:

    """How much of a portfolio is shares, bonds, fund units and cash."""

    totals: dict[str, Decimal] = defaultdict(Decimal)

    for row in rows:
        totals[row.asset_class.value] += row.weight_pct

    return {name: percent(weight) for name, weight in sorted(totals.items(), key=lambda item: item[1], reverse=True)}


def equity_weights(rows: Sequence[FundHolding]) -> dict[str, Decimal]:

    """Each share's weight in a portfolio by its ISIN, joining repeat lines of the same share."""

    weights: dict[str, Decimal] = defaultdict(Decimal)

    for row in rows:

        if row.asset_class == HoldingAssetClass.equity and row.holding_isin:
            weights[row.holding_isin] += row.weight_pct

    return weights


def overlap(
    first: dict[str, Decimal],
    second: dict[str, Decimal],
    ) -> Decimal:

    """The share of two portfolios that is the same stocks: the smaller weight of every stock both hold, added up."""

    return sum((min(first[isin], second[isin]) for isin in first.keys() & second.keys()), Decimal(0))


class MarketService:

    """Read-only queries on stocks, mutual_funds and fund_holdings for one session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the caller's session."""

        self.session = session

    async def search(
        self,
        query: str,
        kind: InstrumentKind,
        filters: SearchFilters,
        limit: int | None,
        ) -> dict[str, Any]:

        """Find stocks, ETFs and fund schemes by name, symbol or ISIN, each fund scheme with all its plans."""

        limit = min(limit or SEARCH_LIMIT, MAX_SEARCH_LIMIT)
        words = words_of(query)
        result: dict[str, Any] = {}

        if kind in (InstrumentKind.any, InstrumentKind.stock, InstrumentKind.etf):
            result["stocks"] = await self.search_stocks(query, words, kind, filters, limit)

        if kind in (InstrumentKind.any, InstrumentKind.fund):
            result["funds"] = await self.search_funds(query, words, filters, limit)

        return result

    async def search_stocks(
        self,
        query: str,
        words: list[str],
        kind: InstrumentKind,
        filters: SearchFilters,
        limit: int,
        ) -> list[dict[str, Any]]:

        """Stocks and ETFs whose name has every word, or whose symbol starts with the query, exact symbols first, then biggest."""

        exact = query.strip().upper()
        compact = exact.replace(" ", "")
        statement = select(Stock)

        if words:
            by_name = name_matches(select(Stock.id), Stock.company_name, words)
            by_symbol = Stock.symbol.startswith(compact) if len(compact) >= MIN_SYMBOL_PREFIX else Stock.symbol == compact

            statement = statement.where(or_(Stock.id.in_(by_name), by_symbol, Stock.isin == exact))

        if kind == InstrumentKind.stock:
            statement = statement.where(Stock.is_etf.is_(False))

        if kind == InstrumentKind.etf:
            statement = statement.where(Stock.is_etf.is_(True))

        if filters.sector:
            statement = statement.where(Stock.sector == filters.sector)

        if filters.market_cap:
            statement = statement.where(Stock.market_cap_type == filters.market_cap)

        exact_first = case((Stock.symbol == compact, 0), else_=1)
        statement = statement.order_by(exact_first, Stock.market_cap_type.nulls_last(), Stock.company_name).limit(limit)

        return [stock_item(stock) for stock in await self.session.scalars(statement)]

    async def search_funds(
        self,
        query: str,
        words: list[str],
        filters: SearchFilters,
        limit: int,
        ) -> list[dict[str, Any]]:

        """Fund schemes whose name has every word, or that have a plan with this ISIN, each with all its plans."""

        exact = query.strip().upper()
        schemes = select(MutualFund.base_scheme_name).where(MutualFund.base_scheme_name.is_not(None))

        if words:
            by_name = name_matches(select(MutualFund.id), MutualFund.scheme_name, words)
            schemes = schemes.where(or_(MutualFund.id.in_(by_name), MutualFund.isin == exact))

        if filters.category:
            schemes = schemes.where(MutualFund.category == filters.category)

        if filters.sub_category:
            schemes = schemes.where(MutualFund.sub_category == filters.sub_category)

        if filters.amc:
            schemes = name_matches(schemes, MutualFund.amc_name, words_of(filters.amc))

        names = list(await self.session.scalars(schemes.distinct().order_by(MutualFund.base_scheme_name).limit(limit)))

        if not names:
            return []

        plans = await self.session.scalars(
            select(MutualFund)
            .where(MutualFund.base_scheme_name.in_(names))
            .order_by(MutualFund.base_scheme_name, MutualFund.plan_type, MutualFund.option_type)
            )

        grouped: dict[str, dict[str, Any]] = {}

        for fund in plans:
            scheme = grouped.setdefault(fund.base_scheme_name, {
                "scheme": fund.base_scheme_name,
                "amc": fund.amc_name,
                "category": fund.category,
                "sub_category": fund.sub_category,
                "plans": [],
                })
            scheme["plans"].append(plan_item(fund))

        return list(grouped.values())

    async def fund_by_isin(self, isin: str) -> MutualFund:

        """The fund plan with this ISIN, or refuse with a message the model can read."""

        fund = await self.session.scalar(select(MutualFund).where(MutualFund.isin == isin.strip().upper()))

        if fund is None:
            raise RecordNotFound(f"No fund plan has ISIN {isin}. Use search_instruments to find it.")

        return fund

    async def portfolio(self, base_scheme_name: str | None) -> list[FundHolding]:

        """Every line of a scheme's latest portfolio, largest first, or nothing when it is not loaded."""

        if base_scheme_name is None:
            return []

        rows = await self.session.scalars(
            select(FundHolding)
            .where(FundHolding.base_scheme_name == base_scheme_name)
            .order_by(FundHolding.weight_pct.desc())
            )

        return list(rows)

    async def fund_details(
        self,
        isin: str,
        top: int | None,
        ) -> dict[str, Any]:

        """One fund plan with its sister plans, top holdings, sector split and asset split."""

        fund = await self.fund_by_isin(isin)

        siblings = await self.session.scalars(
            select(MutualFund)
            .where(MutualFund.base_scheme_name == fund.base_scheme_name)
            .order_by(MutualFund.plan_type, MutualFund.option_type)
            )

        rows = await self.portfolio(fund.base_scheme_name)

        details: dict[str, Any] = {
            "scheme": fund.base_scheme_name or fund.scheme_name,
            "amc": fund.amc_name,
            "category": fund.category,
            "sub_category": fund.sub_category,
            "this_plan": plan_item(fund),
            "all_plans": [plan_item(plan) for plan in siblings],
            "portfolio_available": bool(rows),
            }

        if not rows:
            return details

        details.update({
            "portfolio_date": rows[0].as_of_date,
            "holdings_count": len(rows),
            "asset_split_pct": asset_split(rows),
            "sector_split": sector_split(rows),
            "top_holdings": [
                {
                    "name": row.holding_name,
                    "isin": row.holding_isin,
                    "industry": row.industry,
                    "sector": row.sector,
                    "asset_class": row.asset_class,
                    "weight_pct": percent(row.weight_pct),
                    }
                for row in rows[:min(top or TOP_HOLDINGS, MAX_TOP_HOLDINGS)]
                ],
            })

        return details

    async def stock_details(self, isin_or_symbol: str) -> dict[str, Any]:

        """One stock or ETF with the fund schemes that hold the most of it."""

        key = isin_or_symbol.strip().upper()

        stock = await self.session.scalar(
            select(Stock).where(or_(Stock.isin == key, Stock.symbol == key)).order_by(Stock.exchange).limit(1)
            )

        if stock is None:
            raise RecordNotFound(f"No stock has ISIN or symbol {isin_or_symbol}. Use search_instruments to find it.")

        holders = await self.session.execute(
            select(FundHolding.base_scheme_name, FundHolding.amc_name, FundHolding.weight_pct)
            .where(FundHolding.holding_isin == stock.isin, FundHolding.base_scheme_name.is_not(None))
            .order_by(FundHolding.weight_pct.desc())
            )

        holders = list(holders)

        return {
            **stock_item(stock),
            "schemes_holding": len({row.base_scheme_name for row in holders}),
            "top_schemes_holding": [
                {"scheme": row.base_scheme_name, "amc": row.amc_name, "weight_pct": percent(row.weight_pct)}
                for row in holders[:TOP_FUNDS_HOLDING]
                ],
            }

    async def compare(self, isins: Sequence[str]) -> dict[str, Any]:

        """Two to four funds side by side: their sector splits and how much of their stocks are the same."""

        if not MIN_COMPARE <= len(isins) <= MAX_COMPARE:
            raise RecordNotFound(f"Give {MIN_COMPARE} to {MAX_COMPARE} fund ISINs to compare.")

        funds = [await self.fund_by_isin(isin) for isin in isins]
        portfolios = [await self.portfolio(fund.base_scheme_name) for fund in funds]
        weights = [equity_weights(rows) for rows in portfolios]

        compared = [
            {
                "scheme": fund.base_scheme_name or fund.scheme_name,
                "isin": fund.isin,
                "category": fund.category,
                "sub_category": fund.sub_category,
                "nav": money(fund.last_nav),
                "portfolio_available": bool(rows),
                "equity_holdings": len(weights[index]),
                "asset_split_pct": asset_split(rows),
                "sector_split": sector_split(rows),
                }
            for index, (fund, rows) in enumerate(zip(funds, portfolios))
            ]

        pairs = []

        for left in range(len(funds)):

            for right in range(left + 1, len(funds)):
                common = weights[left].keys() & weights[right].keys()

                pairs.append({
                    "funds": [compared[left]["scheme"], compared[right]["scheme"]],
                    "common_stocks": len(common),
                    "overlap_pct": percent(overlap(weights[left], weights[right])),
                    })

        return {"funds": compared, "overlap": pairs}

    async def describe_holdings(self, holdings: Sequence[Holding]) -> dict[int, dict[str, Any]]:

        """Each holding's stock or fund name, ISIN and latest price, so a list shows what was bought, not an id."""

        stock_ids = {holding.stock_id for holding in holdings if holding.stock_id is not None}
        fund_ids = {holding.mutual_fund_id for holding in holdings if holding.mutual_fund_id is not None}

        stocks = {stock.id: stock for stock in await self.session.scalars(select(Stock).where(Stock.id.in_(stock_ids)))} if stock_ids else {}
        funds = {fund.id: fund for fund in await self.session.scalars(select(MutualFund).where(MutualFund.id.in_(fund_ids)))} if fund_ids else {}

        described: dict[int, dict[str, Any]] = {}

        for holding in holdings:
            stock = stocks.get(holding.stock_id)
            fund = funds.get(holding.mutual_fund_id)

            if stock is not None:
                described[holding.id] = {"name": stock.company_name, "isin": stock.isin, "symbol": stock.symbol, "latest_price": money(stock.last_price), "price_date": stock.price_date}

            elif fund is not None:
                described[holding.id] = {"name": fund.scheme_name, "isin": fund.isin, "latest_nav": money(fund.last_nav), "nav_date": fund.nav_date}

            else:
                continue

            value = self.holding_value(holding, stock, fund)

            if value is not None:
                described[holding.id]["value_today"] = money(value)

        return described

    async def exposure(self, user_id: int) -> dict[str, Any]:

        """The user's stocks and funds added up by asset class and sector, each fund split by its latest portfolio."""

        rows = await self.session.execute(
            select(Holding, Stock, MutualFund)
            .outerjoin(Stock, Holding.stock_id == Stock.id)
            .outerjoin(MutualFund, Holding.mutual_fund_id == MutualFund.id)
            .where(Holding.user_id == user_id)
            )

        by_class: dict[str, Decimal] = defaultdict(Decimal)
        by_sector: dict[str, Decimal] = defaultdict(Decimal)
        total = Decimal(0)
        counted = 0

        for holding, stock, fund in rows:
            value = self.holding_value(holding, stock, fund)

            if value is None or value <= 0:
                continue

            counted += 1
            total += value

            if holding.asset_type == HoldingAssetType.stock:
                self.add_stock(stock, value, by_class, by_sector)
                continue

            portfolio = await self.portfolio(fund.base_scheme_name)
            self.add_fund(fund, portfolio, value, by_class, by_sector)

        if total == 0:
            return {"holdings_counted": 0, "total_value": 0, "by_asset_class": [], "by_sector": []}

        equity_total = by_class.get(HoldingAssetClass.equity.value, Decimal(0))

        return {
            "holdings_counted": counted,
            "total_value": money(total),
            "by_asset_class": [
                {"asset_class": name, "value": money(value), "pct_of_total": percent(value / total * HUNDRED)}
                for name, value in sorted(by_class.items(), key=lambda item: item[1], reverse=True)
                ],
            "by_sector": [
                {
                    "sector": name,
                    "value": money(value),
                    "pct_of_equity": percent(value / equity_total * HUNDRED) if equity_total else 0.0,
                    "pct_of_total": percent(value / total * HUNDRED),
                    }
                for name, value in sorted(by_sector.items(), key=lambda item: item[1], reverse=True)
                ],
            }

    @staticmethod
    def holding_value(
        holding: Holding,
        stock: Stock | None,
        fund: MutualFund | None,
        ) -> Decimal | None:

        """Units at the latest price, falling back to the value saved with the holding."""

        price = stock.last_price if stock is not None else fund.last_nav if fund is not None else None

        if price is not None:
            return holding.units * price

        return holding.current_value

    @staticmethod
    def add_stock(
        stock: Stock,
        value: Decimal,
        by_class: dict[str, Decimal],
        by_sector: dict[str, Decimal],
        ) -> None:

        """Count a directly held share as equity in its own sector, and an ETF as equity not broken down."""

        by_class[HoldingAssetClass.equity.value] += value

        if stock.is_etf:
            by_sector[NOT_BROKEN_DOWN] += value
            return

        by_sector[stock.sector.value if stock.sector else OTHER_SECTOR] += value

    @staticmethod
    def add_fund(
        fund: MutualFund,
        portfolio: Sequence[FundHolding],
        value: Decimal,
        by_class: dict[str, Decimal],
        by_sector: dict[str, Decimal],
        ) -> None:

        """Split a fund's value by its portfolio weights, or count it whole by its category when no portfolio is loaded."""

        if not portfolio:
            name = HoldingAssetClass.equity.value if fund.category == FundCategory.equity else f"{fund.category.value}_fund"
            by_class[name] += value

            if fund.category == FundCategory.equity:
                by_sector[NOT_BROKEN_DOWN] += value

            return

        weight_total = sum((row.weight_pct for row in portfolio), Decimal(0))
        scale = HUNDRED if weight_total <= HUNDRED else weight_total
        rest = value

        for row in portfolio:
            share = value * row.weight_pct / scale
            rest -= share
            by_class[row.asset_class.value] += share

            if row.asset_class == HoldingAssetClass.equity:
                by_sector[row.sector.value if row.sector else OTHER_SECTOR] += share

        if rest > 0:
            by_class[HoldingAssetClass.cash_and_other.value] += rest
