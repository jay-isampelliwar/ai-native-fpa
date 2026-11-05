"""Tell a bank from a mutual fund house by name, so a fund is never saved as a fixed deposit."""

import re

from app.features.records.exceptions import RecordError


FUND_WORDS = (
    "mutual fund",
    "asset management",
    "asset managers",
    "asset mgmt",
    "investment managers",
    "investment management",
    "funds management",
    "money managers",
    "fund house",
    "amc",
    "mf",
    )

FUND_ONLY_BRANDS = (
    "nippon",
    "reliance mutual",
    "mirae",
    "ppfas",
    "parag parikh",
    "dsp",
    "quant",
    "quantum",
    "motilal oswal",
    "franklin",
    "franklin templeton",
    "invesco",
    "edelweiss",
    "uti",
    "groww",
    "zerodha",
    "navi",
    "whiteoak",
    "360 one",
    "samco",
    "pgim",
    "jio blackrock",
    "old bridge",
    "helios",
    "tata mutual",
    "icici prudential",
    "aditya birla sun life",
    "kotak mahindra amc",
    )

SHARED_BRANDS = (
    "axis",
    "hdfc",
    "icici",
    "sbi",
    "state bank",
    "kotak",
    "bandhan",
    "idfc",
    "union",
    "canara",
    "baroda",
    "bank of india",
    "hsbc",
    "lic",
    "bajaj",
    "mahindra",
    "sundaram",
    "shriram",
    "aditya birla",
    "idbi",
    )


def padded(name: str) -> str:

    """The name in lower case with punctuation as spaces and a space at each end, so brands match whole words."""

    return f" {re.sub(r'[^a-z0-9]+', ' ', name.lower()).strip()} "


def has_any(
    name: str,
    words: tuple[str, ...],
    ) -> bool:

    """True when the name holds any of the words as whole words."""

    text = padded(name)

    return any(f" {word} " in text for word in words)


def is_fund_house(name: str) -> bool:

    """True when the name can only be a mutual fund house, such as 'Nippon' or 'Axis Mutual Fund'."""

    return has_any(name, FUND_WORDS) or has_any(name, FUND_ONLY_BRANDS)


def is_shared_brand(name: str | None) -> bool:

    """True when the name is a bank that also runs mutual funds, such as Axis or HDFC, and is not clearly a fund house."""

    return bool(name) and not is_fund_house(name) and has_any(name, SHARED_BRANDS)


def refuse_fund_house(name: str) -> None:

    """Refuse a deposit whose bank name is a mutual fund house, saying where funds are saved."""

    if is_fund_house(name):
        raise RecordError(
            f"'{name}' is a mutual fund house, not a bank, so this was not saved as a fixed deposit. "
            "Tell the user, and save mutual funds with add_stock_or_fund."
            )
