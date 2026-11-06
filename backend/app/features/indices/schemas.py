"""The indices the app can quote, their Yahoo symbols and display names, and the shape of one quote."""

from dataclasses import dataclass
from enum import StrEnum


class IndexName(StrEnum):

    """An index the app can quote."""

    nifty_50 = "nifty_50"
    sensex = "sensex"
    bank_nifty = "bank_nifty"


YAHOO_SYMBOLS: dict[IndexName, str] = {
    IndexName.nifty_50: "^NSEI",
    IndexName.sensex: "^BSESN",
    IndexName.bank_nifty: "^NSEBANK",
    }

DISPLAY_NAMES: dict[IndexName, str] = {
    IndexName.nifty_50: "NIFTY 50",
    IndexName.sensex: "SENSEX",
    IndexName.bank_nifty: "NIFTY BANK",
    }


@dataclass(frozen=True)
class IndexQuote:

    """One index's level now, today's open, high and low, the last session's close, and when the market opens and shuts."""

    index: IndexName
    name: str
    value: float
    previous_close: float
    open: float | None
    high: float | None
    low: float | None
    as_of: int
    session_start: int
    session_end: int


class QuoteUnavailable(Exception):

    """Yahoo could not be reached, timed out, or sent data that cannot make a quote."""
