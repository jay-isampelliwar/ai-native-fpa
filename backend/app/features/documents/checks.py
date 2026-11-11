"""Checking every parsed row: needed fields, matching stocks and funds, duplicates, saved records, and questions where unsure."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ImportRowAction, ImportRowStatus
from app.db.models import Document, Holding, ImportRow, User
from app.db.session import Base
from app.features.documents.matching import choice_label, find_instrument, instrument_by_answer
from app.features.documents.normalize import header_key
from app.features.documents.records import (
    MATCH_KEYS,
    by_keys,
    changes,
    column_values,
    comparable_fields,
    label,
    saved_records,
    )
from app.features.documents.repository import DocumentRepository
from app.features.documents.rules import (
    keep_answers,
    mismatch_question,
    open_count,
    option,
    question,
    required_errors,
    value_errors,
    )


NEW = "new"
KEEP = "keep"
SKIP = "skip"
NONE_OF_THESE = "none"


@dataclass
class RowState:

    """One row while it is being checked: its effective values and everything found so far."""

    row: ImportRow
    data: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    resolved: dict[str, Any] = field(default_factory=dict)
    action: ImportRowAction | None = None
    target: Base | None = None
    skipped: bool = False

    @property
    def number(self) -> int:

        """The row's number in the file."""

        return self.row.row_number

    def ask(self, item: dict[str, Any]) -> str | None:

        """Add a question, keeping the user's earlier answer to it, and return that answer."""

        kept = keep_answers([item], self.row.questions or [])[0]
        self.questions.append(kept)

        return kept["answer"]


def checkable(row: ImportRow) -> bool:

    """Whether a row is still open to checks: proposed, or skipped earlier by the user's own answer."""

    return row.status == ImportRowStatus.proposed or (row.status == ImportRowStatus.rejected and bool((row.resolved or {}).get("skipped")))


def start(row: ImportRow) -> RowState:

    """Begin a row's checks from its parsed values with the user's edits on top, and its basic field checks."""

    edited = row.edited_data or {}
    data = {**row.parsed_data, **edited}
    read_errors = [error for error in (row.source or {}).get("read_errors", []) if error.split(":")[0] not in edited]
    state = RowState(row=row, data=data, errors=read_errors)
    state.errors += required_errors(row.target_table, data)
    state.errors += value_errors(data)

    return state


def folio_of(value: Any) -> str:

    """A folio number tidied for comparing, empty when there is none."""

    return header_key(value).replace(" ", "") if value else ""


class Checker:

    """Runs every check for one document's rows against one user's saved records."""

    def __init__(
        self,
        session: AsyncSession,
        user_id: int
        ) -> None:

        """Keep the session, the user, and a cache of their saved records by table."""

        self.session = session
        self.user_id = user_id
        self.saved: dict[str, list[Base]] = {}

    async def records(self, table: str) -> list[Base]:

        """The user's saved records of one table, read once per run."""

        if table not in self.saved:
            self.saved[table] = await saved_records(self.session, table, self.user_id)

        return self.saved[table]

    async def run(self, rows: list[ImportRow]) -> list[RowState]:

        """Check holdings first, then the rows that hang off them, then everything else."""

        states = [start(row) for row in rows if checkable(row)]
        by_number = {state.number: state for state in states}
        holdings = [state for state in states if state.row.target_table == "holdings"]

        for state in holdings:
            await self.match_instrument(state)

        self.mark_duplicates(holdings)

        for state in holdings:
            self.check_value(state)
            await self.match_holding(state)

        for state in states:

            table = state.row.target_table

            if table == "sip_plans":
                await self.match_sip(state, by_number)

            elif table == "users":
                await self.settle(state, await self.session.get(User, self.user_id))

            elif table in MATCH_KEYS:
                await self.match_record(state)

        return states

    async def match_instrument(self, state: RowState) -> None:

        """Find the stock or fund: certain by ISIN or symbol, otherwise a question with the closest choices."""

        found = await find_instrument(self.session, state.data)

        if found.error:
            state.errors.append(found.error)
            return

        if found.instrument:
            self.use_instrument(state, found.instrument)
            return

        name = state.data.get("security_name")
        options = [option(f"{choice['kind']}:{choice['id']}", choice_label(choice)) for choice in found.choices]
        options.append(option(NONE_OF_THESE, "None of these"))
        answer = state.ask(question(f"instrument:{state.number}", "pick_instrument", f"Which fund or stock is '{name}'?", options))

        if answer == NONE_OF_THESE:
            state.errors.append(f"security_name: you said no choice matches '{name}'. Add the ISIN, or reject this row.")

        elif answer:
            self.use_instrument(state, await instrument_by_answer(self.session, answer))

    def use_instrument(
        self,
        state: RowState,
        instrument: dict[str, Any] | None
        ) -> None:

        """Keep the matched stock or fund, and set the holding's type from it, since an ETF can sit in a funds sheet."""

        if instrument is None:
            state.errors.append("security_name: the chosen stock or fund no longer exists. Pick again.")
            return

        state.resolved["instrument"] = instrument
        state.data["asset_type"] = "stock" if instrument["kind"] == "stock" else "mutual_fund"

    def mark_duplicates(self, holdings: list[RowState]) -> None:

        """Ask about each line when the same fund or stock appears more than once with the same folio, or no folio."""

        groups: dict[tuple[str, int, str], list[RowState]] = {}

        for state in holdings:

            instrument = state.resolved.get("instrument")

            if instrument:
                key = (instrument["kind"], instrument["id"], folio_of(state.data.get("folio_number")))
                groups.setdefault(key, []).append(state)

        for group in groups.values():

            if len(group) < 2:
                continue

            numbers = ", ".join(str(state.number) for state in group)

            for state in group:

                name = state.resolved["instrument"]["name"]
                text = f"{name} appears {len(group)} times in this file (rows {numbers}). Keep row {state.number}?"
                answer = state.ask(question(f"duplicate:{state.number}", "keep_duplicate", text, [option(KEEP, "Keep this line"), option(SKIP, "Skip this line")]))
                state.skipped = answer == SKIP

    def check_value(self, state: RowState) -> None:

        """Ask which value is right when units times price disagrees with the value given."""

        if state.skipped:
            return

        item = mismatch_question(state.number, state.data)

        if item is None:
            return

        answer = state.ask(item)

        if answer:
            state.data["current_value"] = answer
            state.resolved["current_value"] = answer

    async def match_holding(self, state: RowState) -> None:

        """Find the saved holding of the same fund or stock and folio, asking whenever the folios leave a doubt."""

        instrument = state.resolved.get("instrument")

        if state.skipped or not instrument:
            return

        column = Holding.stock_id if instrument["kind"] == "stock" else Holding.mutual_fund_id
        saved = [holding for holding in await self.records("holdings") if getattr(holding, column.key) == instrument["id"]]
        folio = folio_of(state.data.get("folio_number"))
        name = instrument["name"]

        if folio:

            same_folio = [holding for holding in saved if folio_of(holding.folio_number) == folio]

            if same_folio:
                await self.choose(state, same_folio, f"You have more than one saved {name} with folio {folio}. Which one does row {state.number} update?")
                return

            no_folio = [holding for holding in saved if not holding.folio_number]

            if not no_folio:
                await self.settle(state, None)
                return

            await self.choose(state, no_folio, f"Your saved {name} has no folio. Is it the same holding as folio {folio} in the file?", always_ask=True)
            return

        if len(saved) == 1 and not saved[0].folio_number:
            await self.settle(state, saved[0])
            return

        if not saved:
            await self.settle(state, None)
            return

        await self.choose(state, saved, f"Row {state.number} has no folio. Is {name} in the file one of your saved holdings?", always_ask=True)

    async def match_sip(
        self,
        state: RowState,
        by_number: dict[int, RowState]
        ) -> None:

        """A SIP goes with its holding row: new with a new holding, or matched against that holding's saved SIPs."""

        parent = by_number.get(state.data.get("holding_row_number"))

        if parent is None or parent.skipped:
            state.errors.append("holding: this SIP's holding row is skipped or not ready")
            return

        if parent.action is None:
            return

        if parent.action == ImportRowAction.create:
            await self.settle(state, None)
            return

        holding_id = parent.target.id if parent.target is not None else None
        saved = [sip for sip in await self.records("sip_plans") if sip.holding_id == holding_id and sip.is_active]
        await self.choose(state, saved, f"You have more than one active SIP into this holding. Which one does row {state.number} update?")

    async def match_record(self, state: RowState) -> None:

        """Match by type and name: none means new, one means that record, more than one means a question."""

        table = state.row.target_table
        matched = by_keys(table, state.data, await self.records(table))

        if matched is None:
            return

        await self.choose(state, matched, f"You have more than one saved record like row {state.number}. Which one does it update?")

    async def choose(
        self,
        state: RowState,
        candidates: list[Base],
        text: str,
        always_ask: bool = False
        ) -> None:

        """Settle on the one candidate, or ask the user which one, or whether it is new, when there is any doubt."""

        if not candidates:
            await self.settle(state, None)
            return

        if len(candidates) == 1 and not always_ask:
            await self.settle(state, candidates[0])
            return

        table = state.row.target_table
        options = [option(f"record:{record.id}", label(table, record)) for record in candidates]
        options.append(option(NEW, "No, add it as a new one"))
        answer = state.ask(question(f"record:{state.number}", "pick_record", text, options))

        if answer is None:
            return

        chosen = next((record for record in candidates if answer == f"record:{record.id}"), None)
        await self.settle(state, chosen)

    async def settle(
        self,
        state: RowState,
        record: Base | None
        ) -> None:

        """Fix the row's action: create with no saved record, otherwise update or no change by comparing values."""

        if record is None:
            state.action = ImportRowAction.create
            return

        table = state.row.target_table
        diff = changes(table, state.data, record)
        state.target = record
        state.action = ImportRowAction.update if diff else ImportRowAction.no_change
        state.resolved["existing"] = column_values(record, comparable_fields(table, state.data))
        state.resolved["changes"] = diff


def finish(state: RowState) -> None:

    """Write the checks back onto the row, rejecting it when the user chose to skip it."""

    row = state.row
    state.resolved["skipped"] = state.skipped
    row.errors = state.errors
    row.questions = state.questions
    row.resolved = state.resolved
    row.action = None if state.skipped else state.action
    row.target_record_id = state.target.id if state.target is not None and not state.skipped else None
    row.status = ImportRowStatus.rejected if state.skipped else ImportRowStatus.proposed


def ready(row: ImportRow) -> bool:

    """Whether a row could be approved: no errors, no open questions, an action, and not skipped."""

    return row.status == ImportRowStatus.proposed and not row.errors and not open_count(row.questions) and row.action is not None


async def run_checks(
    session: AsyncSession,
    document: Document
    ) -> None:

    """Check all of a document's open rows and store the counts the review screen shows."""

    rows = await DocumentRepository(session).rows(document.id)

    for state in await Checker(session, document.user_id).run(rows):
        finish(state)

    document.summary = {**document.summary, "checks": counts(rows)}


def counts(rows: list[ImportRow]) -> dict[str, int]:

    """How many rows are ready, blocked by errors, waiting on questions, or skipped."""

    return {
        "ready": sum(1 for row in rows if ready(row)),
        "with_errors": sum(1 for row in rows if row.status == ImportRowStatus.proposed and row.errors),
        "open_questions": sum(open_count(row.questions) for row in rows if row.status == ImportRowStatus.proposed),
        "skipped": sum(1 for row in rows if row.status == ImportRowStatus.rejected),
        "no_change": sum(1 for row in rows if row.action == ImportRowAction.no_change),
        }
