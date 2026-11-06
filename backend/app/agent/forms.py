"""The input forms the agent can open, the fields each one may prefill, and the message a filled form sends to the agent."""

from enum import StrEnum
from typing import Any

from app.agent.cards import label_of
from app.features.records.kinds import RecordKind


FORM_PREFIX = "Form submitted:"

EDIT_MARK = "Change the saved item"


class FormKind(StrEnum):

    """Every form the frontend knows how to draw."""

    goal = "goal"
    income = "income"
    expense = "expense"
    holding = "holding"
    loan = "loan"
    insurance = "insurance"


FORM_FIELDS: dict[FormKind, tuple[str, ...]] = {
    FormKind.goal: ("goal_type", "name", "target_amount", "target_year", "priority", "family_member_name"),
    FormKind.income: ("source_type", "name", "amount", "frequency", "yearly_growth_rate", "start_date"),
    FormKind.expense: ("category", "name", "amount", "frequency", "is_essential", "end_date"),
    FormKind.holding: ("instrument_name", "plan", "units", "amount", "folio_number"),
    FormKind.loan: ("loan_type", "lender", "principal", "outstanding", "interest_rate", "emi", "start_date", "end_date"),
    FormKind.insurance: (
        "policy_type",
        "insurer",
        "cover_amount",
        "premium",
        "premium_frequency",
        "policy_name",
        "start_date",
        "renewal_date",
        ),
    }

FORM_TITLES = {
    FormKind.goal: "Goal",
    FormKind.income: "Income",
    FormKind.expense: "Expense",
    FormKind.holding: "Stock or mutual fund",
    FormKind.loan: "Loan",
    FormKind.insurance: "Insurance policy",
    }

FORM_RECORD_KINDS = {
    FormKind.goal: RecordKind.goals,
    FormKind.income: RecordKind.income,
    FormKind.expense: RecordKind.expenses,
    FormKind.holding: RecordKind.holdings,
    FormKind.loan: RecordKind.loans,
    FormKind.insurance: RecordKind.insurance,
    }

FORM_TOOLS = {
    FormKind.goal: "add_goal",
    FormKind.income: "add_income_source",
    FormKind.expense: "add_expense",
    FormKind.holding: "search_stocks_and_funds, then add_stock_or_fund",
    FormKind.loan: "add_loan",
    FormKind.insurance: "add_insurance_policy",
    }

EXTRA_LABELS = {
    "instrument_name": "Stock or fund name",
    "plan": "Plan",
    "amount": "Amount",
    "family_member_name": "For family member",
    }


def known_values(
    kind: FormKind,
    values: dict[str, Any] | None,
    ) -> dict[str, Any]:

    """Keep only the filled-in values this form has a field for."""

    allowed = FORM_FIELDS[kind]

    return {name: value for name, value in (values or {}).items() if name in allowed and value not in (None, "")}


def field_label(name: str) -> str:

    """The plain-words label for one form field."""

    return EXTRA_LABELS.get(name, label_of(name))


def form_text(
    kind: FormKind,
    values: dict[str, Any],
    record_id: int | None,
    ) -> str:

    """The message the agent reads when the user sends a filled form: what it is, each value, and what to do with it."""

    filled = known_values(kind, values)

    lines = [f"{FORM_PREFIX} {kind.value}", f"I filled in the {FORM_TITLES[kind].lower()} form with these details:"]

    lines.extend(f"- {name} ({field_label(name)}): {value}" for name, value in filled.items())

    if record_id is not None:
        lines.append(
            f"{EDIT_MARK} of kind {FORM_RECORD_KINDS[kind].value} with id {record_id}. "
            "Call update_record with only the fields that differ from what is saved."
            )

    else:
        lines.append(f"Check them and save them with {FORM_TOOLS[kind]}.")

    return "\n".join(lines)


def is_form_text(text: str) -> bool:

    """True when the message was sent by a filled form."""

    return text.startswith(FORM_PREFIX)


def is_edit_form(text: str) -> bool:

    """True when a filled form changes an item that is already saved."""

    return is_form_text(text) and EDIT_MARK in text
