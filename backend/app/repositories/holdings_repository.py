"""Ownership scoped reads of what a user actually owns, and what their statements said it was worth.

Holdings are the one record type where the honest answer has two halves. ``invested_value`` is what
was paid and does not change; ``current_value`` is what a statement said on the day it was exported.
Neither is a live price, and this repository does not pretend otherwise - it returns ``as_of`` beside
every figure so a caller can say how stale the valuation is rather than implying it is current.

Totals are computed in the database rather than by summing in Python. A portfolio screen wants one
number per column, and pulling a hundred and forty five rows back to add them up is work the database
already knows how to do.

Rows come back grouped by asset type because that is how the question is asked. Nobody wants a flat
list of a hundred instruments; they want to know how much is equity, how much is funds, and which
positions are large enough to matter.

Ownership is a ``WHERE user_id`` on every query, as everywhere else. Inactive holdings are excluded on
read, because a position that was sold is still history but is not part of what someone owns now.

The asset type grouping labels its expression and groups by that label rather than repeating the
``coalesce`` in both clauses. Repeating it emits two separate bind parameters, and PostgreSQL then
sees two different expressions and rejects the grouping - which is a runtime failure on an endpoint
that type checks perfectly.
"""

from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db.session import session_scope
from app.models.orm.investments import HoldingRow


class HoldingRead(BaseModel):

    """One position, carrying what was paid, what a statement said it was worth, and when."""

    model_config = {"arbitrary_types_allowed": True}

    id: str
    instrument_name: str
    isin: str | None = None
    identifier_type: str = "symbol"
    asset_type: str | None = None
    account_label: str | None = None
    source: str | None = None
    folio_id: str | None = None

    units: Decimal
    average_cost: Decimal
    last_price: Decimal | None = None
    invested_value: Decimal | None = None
    current_value: Decimal | None = None

    as_of: str
    import_batch_id: str | None = None


class HoldingsSummary(BaseModel):

    """A portfolio at a glance, with every figure traceable to the rows that produced it."""

    model_config = {"arbitrary_types_allowed": True}

    count: int = 0
    invested_value: Decimal = Decimal("0")
    current_value: Decimal = Decimal("0")
    unrealised: Decimal = Decimal("0")
    identified_by_isin: int = 0
    valued_at: str | None = None

    by_asset_type: dict[str, Decimal] = Field(default_factory=dict)
    holdings: list[HoldingRead] = Field(default_factory=list)


class HoldingsRepository:

    """Reads one user's active positions and totals them without inventing a current price."""

    async def summary(self, user_id: int, limit: int = 500) -> HoldingsSummary:

        """Return this user's holdings with their totals, dated by the newest statement they came from."""

        async with session_scope() as session:

            rows = (
                await session.scalars(
                    select(HoldingRow)
                    .where(HoldingRow.user_id == user_id, HoldingRow.active.is_(True))
                    .order_by(HoldingRow.current_value.desc().nullslast())
                    .limit(limit)
                )
            ).all()

            totals = (
                await session.execute(
                    select(
                        func.count(),
                        func.coalesce(func.sum(HoldingRow.invested_value), 0),
                        func.coalesce(func.sum(HoldingRow.current_value), 0),
                        func.count().filter(HoldingRow.identifier_type == "isin"),
                        func.max(HoldingRow.as_of),
                    ).where(HoldingRow.user_id == user_id, HoldingRow.active.is_(True))
                )
            ).one()

            bucket = func.coalesce(HoldingRow.asset_type, "unknown").label("bucket")
            bucket_value = func.coalesce(func.sum(HoldingRow.current_value), 0).label("bucket_value")

            by_type = (
                await session.execute(
                    select(bucket, bucket_value)
                    .where(HoldingRow.user_id == user_id, HoldingRow.active.is_(True))
                    .group_by(bucket)
                    .order_by(bucket_value.desc())
                )
            ).all()

        count, invested, current, isin_count, newest = totals

        return HoldingsSummary(
            count=count,
            invested_value=invested,
            current_value=current,
            unrealised=current - invested,
            identified_by_isin=isin_count,
            valued_at=newest.isoformat() if newest else None,
            by_asset_type={asset_type: value for asset_type, value in by_type},
            holdings=[
                HoldingRead(
                    id=row.id,
                    instrument_name=row.instrument_name,
                    isin=row.isin,
                    identifier_type=row.identifier_type,
                    asset_type=row.asset_type,
                    account_label=row.account_label,
                    source=row.source,
                    folio_id=row.folio_id,
                    units=row.units,
                    average_cost=row.average_cost,
                    last_price=row.last_price,
                    invested_value=row.invested_value,
                    current_value=row.current_value,
                    as_of=row.as_of.isoformat(),
                    import_batch_id=row.import_batch_id,
                )
                for row in rows
            ],
        )


holdings_repository = HoldingsRepository()
