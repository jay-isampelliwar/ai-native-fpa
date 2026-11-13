"""Plain checks on one row's values, and the shape of the questions the user answers when the code is not sure."""

from decimal import Decimal
from typing import Any

from app.features.documents.normalize import to_decimal


REQUIRED: dict[str, tuple[str, ...]] = {
    "users": (),
    "family_members": ("name", "relation"),
    "income_sources": ("name", "source_type", "amount"),
    "expenses": ("name", "category", "amount"),
    "transactions": ("txn_date", "amount", "direction", "category"),
    "holdings": ("units", "as_of_date"),
    "sip_plans": ("amount", "sip_day", "start_date"),
    "bank_accounts": ("bank_name", "account_type", "balance", "as_of_date"),
    "fixed_deposits": ("bank_name", "deposit_type", "principal", "interest_rate", "start_date", "maturity_date"),
    "retirement_accounts": ("account_type", "balance", "as_of_date"),
    "physical_assets": ("name", "asset_type", "current_value"),
    "loans": ("loan_type", "lender", "principal", "outstanding", "interest_rate", "emi", "start_date", "end_date"),
    "credit_cards": ("bank_name", "as_of_date"),
    "insurance_policies": ("policy_type", "insurer", "cover_amount", "premium"),
    "goals": ("name", "goal_type", "target_amount", "target_year"),
    }

POSITIVE = {"units", "amount", "cover_amount"}

NOT_NEGATIVE = {
    "balance",
    "principal",
    "outstanding",
    "emi",
    "premium",
    "current_value",
    "invested_amount",
    "target_amount",
    "maturity_amount",
    "monthly_contribution",
    "purchase_value",
    "credit_limit",
    "current_price",
    "avg_buy_price",
    }

RATE_LIMIT = Decimal(50)

MISMATCH_LIMIT = Decimal("0.01")

SIP_DAYS = range(1, 29)


def required_errors(
    table: str,
    data: dict[str, Any]
    ) -> list[str]:

    """One error for each needed field that is missing."""

    return [f"{name}: missing. Fill it in before approving." for name in REQUIRED[table] if data.get(name) in (None, "")]


def value_errors(data: dict[str, Any]) -> list[str]:

    """Errors for amounts below zero, counts that must be above zero, rates past 50% and SIP days past the 28th."""

    errors = []

    for name, value in data.items():

        if name in POSITIVE and value is not None and to_decimal(value) <= 0:
            errors.append(f"{name}: must be more than zero")

        if name in NOT_NEGATIVE and value is not None and to_decimal(value) < 0:
            errors.append(f"{name}: cannot be below zero")

        if name == "interest_rate" and value is not None and not 0 <= to_decimal(value) <= RATE_LIMIT:
            errors.append(f"{name}: {value}% is not a sensible yearly rate")

    if data.get("sip_day") is not None and int(data["sip_day"]) not in SIP_DAYS:
        errors.append("sip_day: must be a day from 1 to 28")

    return errors


def question(
    question_id: str,
    kind: str,
    text: str,
    options: list[dict[str, str]]
    ) -> dict[str, Any]:

    """One question for the user, with its choices, not yet answered."""

    return {"id": question_id, "kind": kind, "text": text, "options": options, "answer": None}


def option(
    value: str,
    label: str
    ) -> dict[str, str]:

    """One choice of a question."""

    return {"value": value, "label": label}


def keep_answers(
    new: list[dict[str, Any]],
    old: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:

    """Carry each earlier answer onto the same question asked again, when that choice is still offered."""

    answers = {item["id"]: item.get("answer") for item in old}

    for item in new:

        answer = answers.get(item["id"])

        if answer is not None and answer in {choice["value"] for choice in item["options"]}:
            item["answer"] = answer

    return new


def answer_of(
    questions: list[dict[str, Any]],
    question_id: str
    ) -> str | None:

    """The user's answer to one question, or None when it is not answered or not asked."""

    for item in questions:

        if item["id"] == question_id:
            return item.get("answer")

    return None


def open_count(questions: list[dict[str, Any]]) -> int:

    """How many questions still wait for an answer."""

    return sum(1 for item in questions if item.get("answer") is None)


def mismatch_question(
    row_number: int,
    data: dict[str, Any]
    ) -> dict[str, Any] | None:

    """A question when units times price is more than 1% away from the value the file gives."""

    if any(data.get(name) is None for name in ("units", "current_price", "current_value")):
        return None

    value = to_decimal(data["current_value"])
    computed = (to_decimal(data["units"]) * to_decimal(data["current_price"])).quantize(Decimal("0.01"))

    if value == 0 or abs(computed - value) / value <= MISMATCH_LIMIT:
        return None

    return question(
        f"value:{row_number}",
        "value_mismatch",
        f"Units × price is ₹{computed}, but the file says the value is ₹{value}. Which is right?",
        [
            option(str(value), f"₹{value}, as the file says"),
            option(str(computed), f"₹{computed}, units × price"),
            ],
        )
