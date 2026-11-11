"""The fields a file may fill in each record table, what kind of value each one holds, and the words that pick a choice."""

import re
from collections.abc import Callable
from typing import Any

from app.features.documents.normalize import (
    NotReadable,
    header_key,
    to_bool,
    to_date,
    to_int,
    to_isin,
    to_money,
    to_rate,
    to_text,
    to_units,
    to_year,
    )


TABLE_FIELDS: dict[str, dict[str, str]] = {
    "users": {
        "name": "text",
        "date_of_birth": "date",
        "city": "text",
        "retirement_age": "int",
        "life_expectancy": "int",
        "risk_appetite": "risk_appetite",
        },
    "family_members": {
        "name": "text",
        "relation": "family_relation",
        "date_of_birth": "date",
        },
    "income_sources": {
        "name": "text",
        "source_type": "income_source_type",
        "amount": "money",
        "frequency": "payment_frequency",
        },
    "expenses": {
        "name": "text",
        "category": "expense_category",
        "amount": "money",
        "frequency": "payment_frequency",
        "is_essential": "bool",
        },
    "transactions": {
        "txn_date": "date",
        "description": "text",
        "amount": "money",
        "direction": "transaction_direction",
        "debit_amount": "money",
        "credit_amount": "money",
        "category": "transaction_category",
        },
    "holdings": {
        "security_name": "text",
        "plan_hint": "text",
        "isin": "isin",
        "asset_type": "holding_asset_type",
        "folio_number": "text",
        "units": "units",
        "avg_buy_price": "units",
        "current_price": "units",
        "invested_amount": "money",
        "current_value": "money",
        "as_of_date": "date",
        "sip_amount": "money",
        },
    "sip_plans": {
        "amount": "money",
        "sip_day": "int",
        "start_date": "date",
        "holding_row_number": "int",
        },
    "bank_accounts": {
        "bank_name": "text",
        "account_type": "bank_account_type",
        "balance": "money",
        "interest_rate": "rate",
        "as_of_date": "date",
        },
    "fixed_deposits": {
        "bank_name": "text",
        "deposit_type": "deposit_type",
        "principal": "money",
        "interest_rate": "rate",
        "start_date": "date",
        "maturity_date": "date",
        "maturity_amount": "money",
        "monthly_contribution": "money",
        "current_value": "money",
        },
    "retirement_accounts": {
        "account_type": "retirement_account_type",
        "balance": "money",
        "monthly_contribution": "money",
        "employer_contribution": "money",
        "interest_rate": "rate",
        "maturity_date": "date",
        "as_of_date": "date",
        },
    "physical_assets": {
        "name": "text",
        "asset_type": "physical_asset_type",
        "purchase_value": "money",
        "current_value": "money",
        "purchase_date": "date",
        "is_self_occupied": "bool",
        "loan_outstanding": "money",
        },
    "loans": {
        "loan_type": "loan_type",
        "lender": "text",
        "principal": "money",
        "outstanding": "money",
        "interest_rate": "rate",
        "emi": "money",
        "start_date": "date",
        "end_date": "date",
        "tenure_months": "int",
        },
    "credit_cards": {
        "bank_name": "text",
        "credit_limit": "money",
        "outstanding": "money",
        "due_day": "int",
        "as_of_date": "date",
        },
    "insurance_policies": {
        "policy_type": "policy_type",
        "insurer": "text",
        "policy_name": "text",
        "cover_amount": "money",
        "premium": "money",
        "premium_frequency": "payment_frequency",
        "maturity_year": "year",
        "renewal_date": "date",
        "members_covered": "text",
        },
    "goals": {
        "name": "text",
        "goal_type": "goal_type",
        "target_amount": "money",
        "target_year": "year",
        "priority": "priority",
        "inflation_rate": "rate",
        "future_value": "money",
        },
    }

CHOICES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "risk_appetite": [
        ("high", ("aggressive", "high", "very high")),
        ("medium", ("moderate", "balanced", "medium")),
        ("low", ("conservative", "low", "capital protection")),
        ],
    "family_relation": [
        ("spouse", ("spouse", "wife", "husband", "partner")),
        ("child", ("child", "son", "daughter", "kid")),
        ("parent", ("parent", "father", "mother")),
        ("sibling", ("sibling", "brother", "sister")),
        ("other", ("other",)),
        ],
    "income_source_type": [
        ("salary", ("salary", "wages")),
        ("rent", ("rental", "rent")),
        ("business", ("business",)),
        ("freelance", ("freelance", "consulting")),
        ("pension", ("pension",)),
        ("other", ("other", "interest", "dividend")),
        ],
    "payment_frequency": [
        ("half_yearly", ("half yearly", "half-yearly", "semi annual")),
        ("monthly", ("monthly", "month")),
        ("quarterly", ("quarterly", "quarter")),
        ("yearly", ("yearly", "annual", "annually", "year")),
        ],
    "expense_category": [
        ("rent", ("rent",)),
        ("maintenance", ("maintenance", "society")),
        ("household_help", ("maid", "cook", "household help", "driver")),
        ("groceries", ("grocer", "household")),
        ("education", ("education", "school", "fees", "tuition", "college")),
        ("child_care", ("child care", "daycare", "creche")),
        ("elder_care", ("elder",)),
        ("electricity", ("electric", "power bill")),
        ("water", ("water",)),
        ("gas", ("gas", "lpg")),
        ("mobile_internet", ("mobile", "internet", "broadband", "wifi")),
        ("fuel", ("fuel", "petrol", "diesel")),
        ("public_transport", ("transport", "commute", "metro", "bus", "cab", "uber", "ola")),
        ("vehicle_maintenance", ("vehicle", "car service")),
        ("medicines", ("medicine", "pharmacy")),
        ("doctor_visits", ("doctor", "hospital", "medical")),
        ("fitness", ("gym", "fitness")),
        ("dining_out", ("dining", "restaurant")),
        ("food_delivery", ("swiggy", "zomato", "food delivery")),
        ("clothing", ("cloth", "apparel")),
        ("shopping", ("shopping", "amazon", "flipkart")),
        ("electronics", ("electronic", "gadget")),
        ("entertainment", ("entertainment", "movie")),
        ("subscriptions", ("subscription", "netflix", "spotify", "ott")),
        ("travel", ("travel", "vacation", "holiday")),
        ("personal_care", ("personal care", "salon", "grooming")),
        ("pets", ("pet",)),
        ("gifts", ("gift",)),
        ("donations", ("donation", "charity")),
        ("family_support", ("family support", "parents support")),
        ("other", ("other", "utilities", "insurance")),
        ],
    "transaction_direction": [
        ("outflow", ("debit", "withdrawal", "dr", "out", "outflow", "paid")),
        ("inflow", ("credit", "deposit", "cr", "in", "inflow", "received")),
        ],
    "transaction_category": [
        ("bonus", ("bonus",)),
        ("refund", ("refund", "reversal", "cashback")),
        ("gift", ("gift",)),
        ("inheritance", ("inheritance",)),
        ("asset_sale", ("sale of", "asset sale")),
        ("medical", ("hospital", "medical", "pharmacy")),
        ("travel", ("travel", "flight", "irctc", "hotel")),
        ("repair", ("repair",)),
        ("purchase", ("amazon", "flipkart", "purchase", "swiggy", "zomato")),
        ("other", ("other",)),
        ],
    "holding_asset_type": [
        ("mutual_fund", ("mutual fund", "fund", "mf")),
        ("stock", ("stock", "equity", "share", "etf")),
        ],
    "bank_account_type": [
        ("salary", ("salary",)),
        ("current", ("current",)),
        ("savings", ("saving", "sb")),
        ],
    "deposit_type": [
        ("rd", ("rd", "recurring")),
        ("fd", ("fd", "fixed", "term deposit")),
        ],
    "retirement_account_type": [
        ("vpf", ("vpf", "voluntary")),
        ("epf", ("epf", "provident fund", "pf")),
        ("ppf", ("ppf", "public provident")),
        ("nps", ("nps", "national pension")),
        ],
    "physical_asset_type": [
        ("real_estate", ("residential", "commercial", "plot", "land", "flat", "house", "property", "apartment", "villa")),
        ("gold", ("gold", "jewel", "silver")),
        ("vehicle", ("vehicle", "car", "bike", "scooter")),
        ("other", ("other",)),
        ],
    "loan_type": [
        ("home", ("home", "housing", "mortgage")),
        ("car", ("car", "vehicle", "auto")),
        ("education", ("education", "student")),
        ("gold", ("gold",)),
        ("personal", ("personal",)),
        ("other", ("other",)),
        ],
    "policy_type": [
        ("term", ("term",)),
        ("health", ("health", "medical", "mediclaim")),
        ("ulip", ("ulip",)),
        ("life", ("life", "endowment", "money back")),
        ("vehicle", ("vehicle", "motor", "car", "bike")),
        ("other", ("other",)),
        ],
    "goal_type": [
        ("retirement", ("retirement", "retire")),
        ("education", ("education", "college", "school")),
        ("house", ("house", "home", "flat", "property")),
        ("marriage", ("marriage", "wedding")),
        ("emergency", ("emergency",)),
        ("vehicle", ("vehicle", "car", "bike")),
        ("travel", ("travel", "vacation", "trip")),
        ("other", ("other",)),
        ],
    "priority": [
        ("1", ("essential", "high", "must", "critical")),
        ("2", ("important", "medium")),
        ("3", ("aspirational", "low", "nice to have", "optional")),
        ],
    }

READERS: dict[str, Callable[[Any], Any]] = {
    "text": to_text,
    "money": to_money,
    "units": to_units,
    "rate": to_rate,
    "int": to_int,
    "year": to_year,
    "date": to_date,
    "bool": to_bool,
    "isin": to_isin,
    }

AMOUNT_KINDS = {"money", "units"}


def pick_choice(
    kind: str,
    raw: Any
    ) -> str:

    """Pick the choice whose words appear in the text, the first rule winning, and fail when none fits."""

    text = header_key(raw)
    words = set(text.split())

    for value, needles in CHOICES[kind]:

        if text == value or any(matches(needle, text, words) for needle in needles):
            return value

    raise NotReadable(f"is not a known {kind.replace('_', ' ')}")


def matches(
    needle: str,
    text: str,
    words: set[str]
    ) -> bool:

    """Whether a short code matches a whole word, or a longer word or phrase starts a word in the text."""

    if len(needle) <= 3:
        return needle in words

    return re.search(rf"\b{re.escape(needle)}", text) is not None


def read_value(
    kind: str,
    raw: Any
    ) -> Any:

    """Turn one raw cell into the clean value its field kind needs."""

    if kind == "priority":

        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return to_int(raw)

        return int(pick_choice(kind, raw))

    if kind in CHOICES:
        return pick_choice(kind, raw)

    return READERS[kind](raw)


def field_kind(
    table: str,
    field: str
    ) -> str:

    """The kind of value one field of one table holds."""

    return TABLE_FIELDS[table][field]


def amount_fields(table: str) -> list[str]:

    """The fields of a table that hold an amount or a count, used to tell a real row from an empty template row."""

    return [field for field, kind in TABLE_FIELDS[table].items() if kind in AMOUNT_KINDS]
