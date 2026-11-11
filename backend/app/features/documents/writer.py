"""Writing approved rows into the record tables through the domain services, reading each one back, and undoing an import."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.verify import SaveMismatch, confirm_removed, confirm_saved, read_back
from app.db.enums import HoldingAssetType
from app.db.models import ImportRow, User
from app.db.session import Base
from app.features.assets.service import AssetService
from app.features.cash_flow.service import CashFlowService
from app.features.documents.records import MODELS, column_values, same
from app.features.investments.schemas import HoldingCreate, SipPlanCreate
from app.features.investments.service import COVERAGE_SECTION, InvestmentService
from app.features.liabilities.service import LiabilityService
from app.features.planning.service import PlanningService
from app.features.profile.schemas import ProfileUpdate
from app.features.profile.service import ProfileService
from app.features.protection.service import ProtectionService
from app.features.records.exceptions import RecordError, RecordExists
from app.features.records.kinds import KINDS, RecordKind
from app.features.records.record_service import RecordService


TABLE_KINDS: dict[str, RecordKind] = {
    "family_members": RecordKind.family,
    "income_sources": RecordKind.income,
    "expenses": RecordKind.expenses,
    "transactions": RecordKind.transactions,
    "bank_accounts": RecordKind.bank_accounts,
    "fixed_deposits": RecordKind.fixed_deposits,
    "retirement_accounts": RecordKind.retirement_accounts,
    "physical_assets": RecordKind.physical_assets,
    "holdings": RecordKind.holdings,
    "sip_plans": RecordKind.sip_plans,
    "loans": RecordKind.loans,
    "credit_cards": RecordKind.credit_cards,
    "insurance_policies": RecordKind.insurance,
    "goals": RecordKind.goals,
    }

ADDERS = {
    "family_members": lambda session, user_id, item: ProfileService(session).add_family_member(user_id, item),
    "income_sources": lambda session, user_id, item: CashFlowService(session).add_income_source(user_id, item),
    "expenses": lambda session, user_id, item: CashFlowService(session).add_expense(user_id, item),
    "transactions": lambda session, user_id, item: CashFlowService(session).add_transaction(user_id, item),
    "bank_accounts": lambda session, user_id, item: AssetService(session).add_bank_account(user_id, item),
    "fixed_deposits": lambda session, user_id, item: AssetService(session).add_fixed_deposit(user_id, item),
    "retirement_accounts": lambda session, user_id, item: AssetService(session).add_retirement_account(user_id, item),
    "physical_assets": lambda session, user_id, item: AssetService(session).add_physical_asset(user_id, item),
    "loans": lambda session, user_id, item: LiabilityService(session).add_loan(user_id, item),
    "credit_cards": lambda session, user_id, item: LiabilityService(session).add_credit_card(user_id, item),
    "insurance_policies": lambda session, user_id, item: ProtectionService(session).add_policy(user_id, item),
    "goals": lambda session, user_id, item: PlanningService(session).add_goal(user_id, item),
    }

SYSTEM_FIELDS = ("id", "user_id", "created_at", "updated_at")

HOLDING_FIELDS = ("folio_number", "units", "avg_buy_price", "invested_amount", "current_value", "as_of_date")


@dataclass
class Written:

    """What one successful write leaves to store on its row: the record, its old values, and the values written."""

    record_id: int
    previous: dict[str, Any] | None
    written: dict[str, Any]


class RowNotWritten(Exception):

    """A row that could not be written, with a plain reason for the user."""


class UndoBlocked(Exception):

    """An undo that would overwrite changes made after the import, so nothing was undone."""

    def __init__(self, reasons: list[str]) -> None:

        """Keep every row that blocks the undo."""

        super().__init__("; ".join(reasons))
        self.reasons = reasons


def schema_input(
    schema: type[BaseModel],
    data: dict[str, Any]
    ) -> dict[str, Any]:

    """Only the row's fields the service's checked input knows, so helper fields like future_value are left out."""

    return {name: value for name, value in data.items() if name in schema.model_fields and value is not None}


def validation_reason(exc: ValidationError) -> str:

    """The checked input's complaints as one plain line."""

    return "; ".join(f"{'.'.join(str(part) for part in error['loc']) or 'row'}: {error['msg']}" for error in exc.errors())


def record_key(
    model: type[Base],
    record_id: int,
    user_id: int
    ) -> dict[str, Any]:

    """The lookup for reading one saved record back, owner included where the table has one."""

    if model is User:
        return {"id": record_id}

    return {"id": record_id, "user_id": user_id}


def typed(
    model: type[Base],
    name: str,
    value: Any
    ) -> Any:

    """Turn a value kept as text back into the column's own type, for putting old values back on undo."""

    if value is None:
        return None

    kind = model.__table__.columns[name].type.python_type

    if issubclass(kind, Enum):
        return kind(value)

    if kind is Decimal:
        return Decimal(str(value))

    if kind is date:
        return date.fromisoformat(str(value))

    if kind is bool:
        return value if isinstance(value, bool) else str(value).lower() == "true"

    if kind is int:
        return int(value)

    return value


class Writer:

    """Writes one user's approved rows, one at a time, each through its domain service and checked after."""

    def __init__(
        self,
        session: AsyncSession,
        user_id: int
        ) -> None:

        """Keep the session and the user."""

        self.session = session
        self.user_id = user_id

    async def write(
        self,
        row: ImportRow,
        data: dict[str, Any],
        rows_by_number: dict[int, ImportRow]
        ) -> Written:

        """Create or update the row's record, and return what to store on the row once the write has held."""

        if row.target_record_id is None:
            record = await self.create(row, data, rows_by_number)
            previous = None
            model = MODELS[row.target_table]
            fields = [name for name in model.__table__.columns.keys() if name not in SYSTEM_FIELDS]

        else:
            record, previous = await self.update(row, data)
            fields = list(previous)

        return Written(record_id=record.id, previous=previous, written=column_values(record, fields))

    async def create(
        self,
        row: ImportRow,
        data: dict[str, Any],
        rows_by_number: dict[int, ImportRow]
        ) -> Base:

        """Add a new record through its service, then read it back and refuse it when any value differs."""

        table = row.target_table

        if table == "holdings":
            item = self.holding_input(row, data)
            record = await InvestmentService(self.session).repo.add_holding(self.user_id, item)
            await InvestmentService(self.session).mark_provided(self.user_id, COVERAGE_SECTION)

        elif table == "sip_plans":
            item = await self.sip_input(data, rows_by_number)
            record = await InvestmentService(self.session).repo.add_sip_plan(self.user_id, item)
            await InvestmentService(self.session).mark_provided(self.user_id, COVERAGE_SECTION)

        elif table in ADDERS:
            schema = KINDS[TABLE_KINDS[table]].schema
            item = schema(**schema_input(schema, data))
            record = await ADDERS[table](self.session, self.user_id, item)

        else:
            raise RowNotWritten(f"Rows for {table} can only update a saved record")

        model = MODELS[table]

        return await confirm_saved(self.session, model, record_key(model, record.id, self.user_id), item.model_dump())

    def holding_input(
        self,
        row: ImportRow,
        data: dict[str, Any]
        ) -> HoldingCreate:

        """The checked holding for the matched stock or fund, keeping the file's units, value and plan date."""

        instrument = row.resolved.get("instrument")

        if not instrument:
            raise RowNotWritten("No stock or fund is matched for this row")

        is_stock = instrument["kind"] == "stock"

        return HoldingCreate(
            asset_type=HoldingAssetType.stock if is_stock else HoldingAssetType.mutual_fund,
            stock_id=instrument["id"] if is_stock else None,
            mutual_fund_id=None if is_stock else instrument["id"],
            **{name: data[name] for name in HOLDING_FIELDS if data.get(name) is not None},
            )

    async def sip_input(
        self,
        data: dict[str, Any],
        rows_by_number: dict[int, ImportRow]
        ) -> SipPlanCreate:

        """The checked SIP into its holding row's saved holding, refusing a copy of an active SIP."""

        parent = rows_by_number.get(data.get("holding_row_number"))

        if parent is None or parent.target_record_id is None or parent.written_at is None:
            raise RowNotWritten("This SIP's holding was not saved, so the SIP cannot be saved")

        item = SipPlanCreate(holding_id=parent.target_record_id, **schema_input(SipPlanCreate, data))
        same_sip = await InvestmentService(self.session).repo.active_sip(self.user_id, item.holding_id, item.amount, item.sip_day)

        if same_sip is not None:
            raise RecordExists("SIP", same_sip.id, "This SIP is already saved")

        return item

    async def update(
        self,
        row: ImportRow,
        data: dict[str, Any]
        ) -> tuple[Base, dict[str, Any]]:

        """Change only the fields that differ, after checking the saved record is still as the preview showed it, returning the old values."""

        table = row.target_table
        model = MODELS[table]
        record = await read_back(self.session, model, record_key(model, row.target_record_id, self.user_id))

        if record is None:
            raise RowNotWritten("The saved record was removed after the preview. Check the document again.")

        seen = row.resolved.get("existing", {})
        moved = [name for name, value in seen.items() if not same(getattr(record, name), value)]

        if moved:
            raise RowNotWritten(f"The saved record changed after the preview ({', '.join(moved)}). Check the document again.")

        names = list(row.resolved.get("changes", {}))
        changes = {name: data.get(name) for name in names}
        previous = column_values(record, names)

        if table == "users":
            await ProfileService(self.session).update_profile(self.user_id, ProfileUpdate(**changes))
            saved = await confirm_saved(self.session, User, {"id": self.user_id}, ProfileUpdate(**changes).model_dump(exclude_none=True))

            return saved, previous

        schema = HoldingCreate if table == "holdings" else KINDS[TABLE_KINDS[table]].schema
        current = {name: getattr(record, name) for name in schema.model_fields if hasattr(record, name)}
        checked = schema(**{**current, **{name: value for name, value in changes.items() if value is not None}})
        fields = {name: getattr(checked, name) for name in names}

        await self.session.execute(
            update(model).where(model.id == record.id, model.user_id == self.user_id).values(**fields)
            )

        saved = await confirm_saved(self.session, model, record_key(model, record.id, self.user_id), fields)

        return saved, previous

    async def undo_blocks(self, rows: list[ImportRow]) -> list[str]:

        """Every written row whose record was changed or removed after the import, which would make undo overwrite the user's work."""

        reasons = []

        for row in rows:

            model = MODELS[row.target_table]
            record = await read_back(self.session, model, record_key(model, row.target_record_id, self.user_id))

            if record is None:
                reasons.append(f"Row {row.row_number}: its saved record was removed after the import")
                continue

            written = row.resolved.get("written", {})
            moved = [name for name, value in written.items() if not same(getattr(record, name), value)]

            if moved:
                reasons.append(f"Row {row.row_number}: you changed {', '.join(moved)} after the import")

        return reasons

    async def undo(self, rows: list[ImportRow]) -> None:

        """Remove what the import created and put back what it changed, newest row first, so SIPs go before their holdings."""

        reasons = await self.undo_blocks(rows)

        if reasons:
            raise UndoBlocked(reasons)

        for row in sorted(rows, key=lambda item: item.row_number, reverse=True):

            model = MODELS[row.target_table]
            key = record_key(model, row.target_record_id, self.user_id)

            if row.previous_data is None:
                await RecordService(self.session).delete_record(self.user_id, TABLE_KINDS[row.target_table], row.target_record_id)
                await confirm_removed(self.session, model, key)
                continue

            old = {name: typed(model, name, value) for name, value in row.previous_data.items()}
            await self.session.execute(update(model).where(*(getattr(model, name) == value for name, value in key.items())).values(**old))
            await confirm_saved(self.session, model, key, old)


WRITE_ERRORS = (RowNotWritten, RecordError, SaveMismatch, ValidationError)


def write_reason(exc: Exception) -> str:

    """A plain reason a row could not be written."""

    if isinstance(exc, ValidationError):
        return f"Not saved: {validation_reason(exc)}"

    if isinstance(exc, SaveMismatch):
        return "Not saved: the check after saving found different values, so this row was undone"

    return f"Not saved: {exc}"
