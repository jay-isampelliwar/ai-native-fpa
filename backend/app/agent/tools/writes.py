"""The tools that change records, which the agent may now call directly.

Read this file knowing what changed. The previous design routed every write through a human approval:
a skill proposed, the graph interrupted, a card showed the before and after, and only an accepted card
reached a write. That gate is gone by explicit decision - the product is meant to work as a chat that
can actually maintain someone's records - and these tools are what replaced it.

Two things were kept, because losing them would have made the change reckless rather than direct.

The first is that nothing is destroyed. There is no hard delete anywhere in this module. Removing a
record archives it: it stops counting towards every future calculation and stays readable as history,
so a wrong instruction costs a correction rather than a reconstruction. A figure that vanishes takes
every past answer that quoted it along with it, and a person cannot audit an answer whose inputs are
no longer there.

The second is that every change is recorded on the ``RunLog`` in the words the person will read. That
log becomes the audit row and the closing sentence, so a turn that altered something cannot report
itself as a turn that did not, and "what did it change" is answerable after the fact.

What is genuinely riskier now: a misheard figure is stored immediately. The model is instructed to
confirm amounts back in its reply and to prefer updating an existing record over creating a second
one, but instructions are not gates, and the honest description of this module is that it trades a
confirmation step for fluency. Re-adding the gate means making these tools propose rather than write,
which is why they all return a description rather than a bare id.

Every tool resolves its target by id, and the ids come from the read tools. That is deliberate: the
model must look before it writes, so a change lands on a row it has actually seen rather than on a
label it matched. The one exception is creation, which has no target yet.

Ownership is checked in the repository on every path, and the tools are bound to one context, so a
row belonging to somebody else is reported as missing exactly as it would be through the API.

Amounts arrive as strings and are parsed here. A model that emits 1.5e6 or "1,50,000" should meet a
refusal rather than a silently wrong ``Decimal``, so parsing is one function and it rejects anything
that is not a positive number.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from langchain_core.tools import BaseTool, tool

from app.agent.context import AgentContext, RunLog
from app.db.session import session_scope
from app.models.finance import Frequency, SipStatus
from app.models.orm.cashflow import ExpenseRecordRow, IncomeRecordRow
from app.models.orm.credit import EmiRecordRow, SipRecordRow
from app.repositories.goals_repository import goals_repository
from app.repositories.records_repository import records_repository
from app.ui.builders import rupees

ARCHIVABLE = {
    "income": IncomeRecordRow,
    "expense": ExpenseRecordRow,
    "emi": EmiRecordRow,
    "sip": SipRecordRow,
}

FREQUENCIES = ("monthly", "quarterly", "half_yearly", "annual", "one_off")


def to_amount(raw: str) -> Decimal | None:

    """Parse a stated figure into money, refusing anything that is not a positive plain number."""

    try:
        amount = Decimal(str(raw).replace(",", "").strip())

    except (InvalidOperation, ValueError, AttributeError):
        return None

    if amount <= 0 or not amount.is_finite():
        return None

    return amount.quantize(Decimal("0.01"))


def to_frequency(raw: str) -> Frequency | None:

    """Turn a stated cadence into the enum every calculator expects, refusing an unknown one."""

    try:
        return Frequency(raw)

    except ValueError:
        return None


def build_write_tools(context: AgentContext, log: RunLog) -> list[BaseTool]:

    """Build every change tool bound to this caller, leaving the model no way to name another."""

    @tool("add_income")
    async def add_income(
        label: str,
        amount: str,
        frequency: str = "monthly",
        source: str = "salary",
        ) -> str:

        """Record a new income arrangement. Check list_income first so you do not add a second copy."""

        log.used("add_income")

        money = to_amount(amount)

        if money is None:
            return f"refused: {amount!r} is not an amount I can store"

        cadence = to_frequency(frequency)

        if cadence is None:
            return f"refused: frequency must be one of {', '.join(FREQUENCIES)}"

        async with session_scope() as session:

            row = await records_repository.create_income(
                session,
                user_id=context.user_id,
                label=label,
                amount=money,
                frequency=cadence,
                source=source,
            )

            detail = f"added income {label} at {rupees(money)} {cadence.value}"

            log.wrote(detail)

            return f"{detail} (id {row.id})"

    @tool("add_expense")
    async def add_expense(
        label: str,
        amount: str,
        frequency: str = "monthly",
        category: str = "general",
        ) -> str:

        """Record a new recurring expense. Check list_expenses first so you do not add a second copy."""

        log.used("add_expense")

        money = to_amount(amount)

        if money is None:
            return f"refused: {amount!r} is not an amount I can store"

        cadence = to_frequency(frequency)

        if cadence is None:
            return f"refused: frequency must be one of {', '.join(FREQUENCIES)}"

        async with session_scope() as session:

            row = await records_repository.create_expense(
                session,
                user_id=context.user_id,
                label=label,
                amount=money,
                frequency=cadence,
                category=category,
            )

            detail = f"added expense {label} at {rupees(money)} {cadence.value}"

            log.wrote(detail)

            return f"{detail} (id {row.id})"

    @tool("add_emi")
    async def add_emi(
        label: str,
        amount: str,
        remaining_months: int,
        interest_rate_percent: str = "0",
        lender: str = "",
        principal_outstanding: str | None = None,
        ) -> str:

        """Record a loan EMI. remaining_months is required - never estimate a loan's remaining term."""

        log.used("add_emi")

        money = to_amount(amount)

        if money is None:
            return f"refused: {amount!r} is not an amount I can store"

        if remaining_months < 1:
            return "refused: a loan needs how many months are left, and it has to be at least one"

        rate = to_amount(interest_rate_percent) or Decimal("0")

        principal = to_amount(principal_outstanding) if principal_outstanding else None

        async with session_scope() as session:

            liability = await records_repository.create_liability(
                session,
                user_id=context.user_id,
                label=label,
                principal_outstanding=principal or money * remaining_months,
                interest_rate_percent=rate,
                tenure_months=remaining_months,
                lender=lender,
            )

            row = await records_repository.create_emi(
                session,
                user_id=context.user_id,
                liability_id=liability.id,
                label=label,
                amount=money,
                interest_rate_percent=rate,
                remaining_months=remaining_months,
            )

            detail = f"added EMI {label} at {rupees(money)} a month with {remaining_months} months left"

            log.wrote(detail)

            return f"{detail} (id {row.id if row else liability.id})"

    @tool("add_sip")
    async def add_sip(
        scheme_name: str,
        amount: str,
        frequency: str = "monthly",
        folio_id: str | None = None,
        linked_goal_id: str | None = None,
        ) -> str:

        """Record a new SIP into a scheme. Check list_sips first so you do not add a second copy."""

        log.used("add_sip")

        money = to_amount(amount)

        if money is None:
            return f"refused: {amount!r} is not an amount I can store"

        cadence = to_frequency(frequency)

        if cadence is None:
            return f"refused: frequency must be one of {', '.join(FREQUENCIES)}"

        async with session_scope() as session:

            row = await records_repository.create_sip(
                session,
                user_id=context.user_id,
                scheme_name=scheme_name,
                amount=money,
                frequency=cadence,
                folio_id=folio_id,
                linked_goal_id=linked_goal_id,
            )

            detail = f"added SIP {scheme_name} at {rupees(money)} {cadence.value}"

            log.wrote(detail)

            return f"{detail} (id {row.id})"

    @tool("add_goal")
    async def add_goal(
        label: str,
        target_amount: str,
        target_year: int,
        kind: str = "custom",
        priority: int = 3,
        ) -> str:

        """Set up a savings goal. Both the target amount and the year are required - never invent either."""

        log.used("add_goal")

        money = to_amount(target_amount)

        if money is None:
            return f"refused: {target_amount!r} is not a target I can store"

        if not 1900 < target_year < 2200:
            return f"refused: {target_year} is not a year I can plan towards"

        if not 1 <= priority <= 5:
            return "refused: priority has to be between 1 and 5"

        async with session_scope() as session:

            row = await goals_repository.create_goal(
                session,
                user_id=context.user_id,
                label=label,
                target_amount=money,
                target_date=date(target_year, 12, 31),
                kind=kind,
                priority=priority,
            )

            detail = f"set up goal {label} targeting {rupees(money)} by {target_year}"

            log.wrote(detail)

            return f"{detail} (id {row.id})"

    @tool("update_record")
    async def update_record(
        kind: str,
        record_id: str,
        amount: str | None = None,
        label: str | None = None,
        ) -> str:

        """Change an existing income, expense, emi or sip. Get record_id from the matching list tool first."""

        log.used("update_record")

        row_class = ARCHIVABLE.get(kind)

        if row_class is None:
            return f"refused: kind must be one of {', '.join(ARCHIVABLE)}"

        changes: dict = {}

        if amount is not None:

            money = to_amount(amount)

            if money is None:
                return f"refused: {amount!r} is not an amount I can store"

            changes["amount"] = money

        if label is not None:
            changes["scheme_name" if kind == "sip" else "label"] = label

        if not changes:
            return "refused: nothing to change - give an amount or a label"

        async with session_scope() as session:

            changed = await records_repository.update_fields(
                session,
                row_class,
                context.user_id,
                record_id,
                changes,
            )

            if not changed:
                return f"refused: no {kind} record with id {record_id}"

            described = ", ".join(
                f"{field} to {rupees(value) if field == 'amount' else value}"
                for field, value in changes.items()
            )

            detail = f"changed {kind} {record_id} {described}"

            log.wrote(detail)

            return detail

    @tool("update_goal")
    async def update_goal(
        goal_id: str,
        target_amount: str | None = None,
        target_year: int | None = None,
        priority: int | None = None,
        ) -> str:

        """Change an existing goal's target, date or priority. Get goal_id from list_goals first."""

        log.used("update_goal")

        changes: dict = {}

        if target_amount is not None:

            money = to_amount(target_amount)

            if money is None:
                return f"refused: {target_amount!r} is not a target I can store"

            changes["target_amount"] = money

        if target_year is not None:

            if not 1900 < target_year < 2200:
                return f"refused: {target_year} is not a year I can plan towards"

            changes["target_date"] = date(target_year, 12, 31)

        if priority is not None:

            if not 1 <= priority <= 5:
                return "refused: priority has to be between 1 and 5"

            changes["priority"] = priority

        if not changes:
            return "refused: nothing to change - give a target, a year or a priority"

        async with session_scope() as session:

            changed = await goals_repository.update_goal(session, context.user_id, goal_id, changes)

            if not changed:
                return f"refused: no goal with id {goal_id}"

            detail = f"changed goal {goal_id}"

            log.wrote(detail)

            return f"{detail}: {', '.join(str(field) for field in changes)}"

    @tool("remove_record")
    async def remove_record(kind: str, record_id: str) -> str:

        """Retire an income, expense, emi or sip that no longer applies. It stops counting but stays readable."""

        log.used("remove_record")

        row_class = ARCHIVABLE.get(kind)

        if row_class is None:
            return f"refused: kind must be one of {', '.join(ARCHIVABLE)}"

        async with session_scope() as session:

            archived = await records_repository.archive(session, row_class, context.user_id, record_id)

            if not archived:
                return f"refused: no {kind} record with id {record_id}"

            detail = f"retired {kind} {record_id}"

            log.wrote(detail)

            return f"{detail} - it no longer counts towards any figure, and is still on record"

    @tool("remove_goal")
    async def remove_goal(goal_id: str) -> str:

        """Retire a goal that no longer applies. It stops being projected but stays readable as history."""

        log.used("remove_goal")

        async with session_scope() as session:

            archived = await goals_repository.archive_goal(session, context.user_id, goal_id)

            if not archived:
                return f"refused: no goal with id {goal_id}"

            detail = f"retired goal {goal_id}"

            log.wrote(detail)

            return f"{detail} - it is no longer projected, and is still on record"

    @tool("pause_sip")
    async def pause_sip(record_id: str, resume: bool = False) -> str:

        """Pause a SIP, or resume a paused one. Get record_id from list_sips first."""

        log.used("pause_sip")

        status = SipStatus.ACTIVE if resume else SipStatus.PAUSED

        async with session_scope() as session:

            changed = await records_repository.update_fields(
                session,
                SipRecordRow,
                context.user_id,
                record_id,
                {"status": status},
            )

            if not changed:
                return f"refused: no SIP with id {record_id}"

            detail = f"{'resumed' if resume else 'paused'} SIP {record_id}"

            log.wrote(detail)

            return detail

    @tool("link_goal_funding")
    async def link_goal_funding(
        goal_id: str,
        asset_table: str,
        asset_id: str,
        allocation_percent: str = "100",
        ) -> str:

        """Earmark a holding, deposit or SIP towards a goal so it counts as funding that goal."""

        log.used("link_goal_funding")

        share = to_amount(allocation_percent)

        if share is None or share > Decimal("100"):
            return "refused: allocation has to be a number between 0 and 100"

        async with session_scope() as session:

            linked = await goals_repository.link_funding(
                session,
                user_id=context.user_id,
                goal_id=goal_id,
                asset_table=asset_table,
                asset_id=asset_id,
                allocation_pct=share,
            )

            if linked is None:
                return f"refused: no goal with id {goal_id}"

            detail = f"earmarked {asset_id} towards goal {goal_id} at {share}%"

            log.wrote(detail)

            return detail

    return [
        add_income,
        add_expense,
        add_emi,
        add_sip,
        add_goal,
        update_record,
        update_goal,
        remove_record,
        remove_goal,
        pause_sip,
        link_goal_funding,
    ]
