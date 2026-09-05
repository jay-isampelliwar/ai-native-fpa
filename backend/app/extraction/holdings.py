"""The one holdings shape every statement is normalised into, whatever the provider called its columns.

Downstream, a query about a portfolio should not have to know which broker a row came from. This
model is that promise: owner, account, instrument, identifier, asset type, quantity, average cost,
invested value, current value, source and as of date, filled the same way for every format.

Invested and current value are stored, not derived on read, and computed here when a statement did
not supply them. One of the three source formats gives both per row; another gives only quantity and
two prices. Computing at extraction time means the difference stops mattering the moment a row is
staged, and the row records which values were computed rather than read.

Identity is preferred as ISIN and honest when it is not available. Two of three real statements carry
no ISIN at all, so ``identifier_type`` records what the row was actually matched on. A holding keyed
on a scheme name is weaker evidence than one keyed on an ISIN, and saying so is better than treating
them as equivalent and silently merging two different funds with similar names.

Confidence falls when something had to be inferred rather than read. A missing quantity, an
unparseable price or a computed value that disagrees with a supplied one all lower it, and the
reconciliation screen sorts by confidence so a person looks at those first.

Nothing here touches the database. These are candidate rows; staging, reconciliation and commit
happen elsewhere, which is what keeps a misparsed column a rejected row rather than a wrong holding.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

ASSET_TYPES = frozenset({"equity", "mutual_fund", "etf", "gold", "silver", "debt", "unknown"})

TOLERANCE = Decimal("0.02")


class CanonicalHolding(BaseModel):

    """One holding in the shape the database stores, whatever the statement called its columns."""

    model_config = {"arbitrary_types_allowed": True}

    instrument_name: str
    isin: str | None = None
    symbol: str | None = None
    identifier_type: str = "symbol"

    asset_type: str = "unknown"
    account_label: str | None = None
    folio_id: str | None = None
    source: str | None = None

    quantity: Decimal | None = None
    average_cost: Decimal | None = None
    last_price: Decimal | None = None
    invested_value: Decimal | None = None
    current_value: Decimal | None = None

    as_of: date | None = None

    confidence: Decimal = Decimal("1.000")
    issues: list[str] = Field(default_factory=list)
    computed_fields: list[str] = Field(default_factory=list)


def choose_identifier(isin: str | None, symbol: str | None, folio_id: str | None) -> tuple[str, str]:

    """Pick the strongest identifier a row actually has, and say which kind it turned out to be."""

    if isin:
        return isin, "isin"

    if folio_id and symbol:
        return f"{symbol}:{folio_id}", "scheme_folio"

    if symbol:
        return symbol, "symbol"

    return "", "none"


def complete_values(holding: CanonicalHolding) -> CanonicalHolding:

    """Fill invested and current value from quantity and prices when the statement did not supply them."""

    if holding.invested_value is None and holding.quantity is not None and holding.average_cost is not None:
        holding.invested_value = (holding.quantity * holding.average_cost).quantize(Decimal("0.01"))

        holding.computed_fields.append("invested_value")

    if holding.current_value is None and holding.quantity is not None and holding.last_price is not None:
        holding.current_value = (holding.quantity * holding.last_price).quantize(Decimal("0.01"))

        holding.computed_fields.append("current_value")

    if holding.average_cost is None and holding.invested_value is not None and holding.quantity:
        holding.average_cost = (holding.invested_value / holding.quantity).quantize(Decimal("0.0001"))

        holding.computed_fields.append("average_cost")

    return holding


def check_consistency(holding: CanonicalHolding) -> CanonicalHolding:

    """Lower confidence where a supplied value disagrees with what the other columns imply."""

    if holding.quantity is None:
        holding.issues.append("no quantity could be read")
        holding.confidence = min(holding.confidence, Decimal("0.300"))

    if holding.invested_value is None and holding.current_value is None:
        holding.issues.append("neither invested nor current value could be established")
        holding.confidence = min(holding.confidence, Decimal("0.300"))

    if (
        holding.quantity is not None
        and holding.average_cost is not None
        and holding.invested_value is not None
        and "invested_value" not in holding.computed_fields
    ):
        implied = holding.quantity * holding.average_cost

        if implied > Decimal("0") and abs(implied - holding.invested_value) / implied > TOLERANCE:
            holding.issues.append("invested value does not match quantity times average cost")
            holding.confidence = min(holding.confidence, Decimal("0.600"))

    if holding.identifier_type in {"symbol", "none"}:
        holding.confidence = min(holding.confidence, Decimal("0.900"))

    if holding.identifier_type == "none":
        holding.issues.append("this row has no usable identifier")
        holding.confidence = min(holding.confidence, Decimal("0.200"))

    return holding


def finalise(holding: CanonicalHolding) -> CanonicalHolding:

    """Complete a candidate holding and judge how much of it had to be inferred."""

    return check_consistency(complete_values(holding))


def to_payload(holding: CanonicalHolding) -> dict:

    """Render a holding as the staged payload a person reconciles and the commit later writes."""

    return {
        "instrument_name": holding.instrument_name,
        "isin": holding.isin,
        "symbol": holding.symbol,
        "identifier_type": holding.identifier_type,
        "asset_type": holding.asset_type,
        "account_label": holding.account_label,
        "folio_id": holding.folio_id,
        "source": holding.source,
        "quantity": str(holding.quantity) if holding.quantity is not None else None,
        "average_cost": str(holding.average_cost) if holding.average_cost is not None else None,
        "last_price": str(holding.last_price) if holding.last_price is not None else None,
        "invested_value": str(holding.invested_value) if holding.invested_value is not None else None,
        "current_value": str(holding.current_value) if holding.current_value is not None else None,
        "as_of": holding.as_of.isoformat() if holding.as_of else None,
        "computed_fields": holding.computed_fields,
    }
