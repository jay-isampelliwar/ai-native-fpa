"""The form path: endpoints that put a user's financial records into the database.

This router is deliberately separate from the planner. Records enter through validated
requests a person filled in, and the conversation reads them; keeping the two surfaces apart
is what stops "chat wrote this row" from ever becoming possible by accident. When Phase 5
lets an approved proposal write, it goes through the approval gate and the same repository,
not through these endpoints.

Every handler opens one ``session_scope`` and does all its work inside it. The repository
stages changes and never commits, so a create that succeeds and a follow up that fails roll
back together rather than leaving half a record behind.

Ownership failures return 404 rather than 403. Telling a caller that a record exists but
belongs to someone else is itself a disclosure, so a record the caller does not own is
reported exactly as one that does not exist.

Archiving is a POST to ``/archive`` rather than a DELETE, because nothing here deletes. The
verb matching the actual effect keeps a client from assuming the row is gone and building a
UI that hides history the audit trail still points at.
"""

from fastapi import APIRouter, HTTPException

from app.api.v1.records.schemas import (
    ArchiveRequest,
    EmiCreate,
    ExpenseCreate,
    ExpenseUpdate,
    IncomeCreate,
    IncomeUpdate,
    LiabilityCreate,
    RecordChanged,
    RecordCreated,
    SipCreate,
    TransactionCreate,
)
from app.db.session import session_scope
from app.models.orm.cashflow import ExpenseRecordRow, ExpenseTransactionRow, IncomeRecordRow
from app.models.orm.credit import EmiRecordRow, LiabilityRow, SipRecordRow
from app.repositories.records_repository import records_repository

router = APIRouter(prefix="/records", tags=["records"])

ARCHIVABLE = {
    "income": IncomeRecordRow,
    "expenses": ExpenseRecordRow,
    "liabilities": LiabilityRow,
    "emis": EmiRecordRow,
    "sips": SipRecordRow,
}


@router.post("/income", response_model=RecordCreated, status_code=201)
async def create_income(request: IncomeCreate) -> RecordCreated:

    """Record one income arrangement and return the identifier a skill will later quote as evidence."""

    async with session_scope() as session:
        row = await records_repository.create_income(
            session,
            user_id=request.user_id,
            label=request.label,
            amount=request.amount,
            frequency=request.frequency,
            source=request.source,
        )

        return RecordCreated(id=row.id, kind="income")


@router.patch("/income/{record_id}", response_model=RecordChanged)
async def update_income(record_id: str, request: IncomeUpdate, user_id: int) -> RecordChanged:

    """Apply only the fields the client actually sent, leaving every other one untouched."""

    async with session_scope() as session:
        changed = await records_repository.update_fields(
            session,
            IncomeRecordRow,
            user_id,
            record_id,
            request.model_dump(exclude_unset=True),
        )

    if not changed:
        raise HTTPException(status_code=404, detail="no such record")

    return RecordChanged(id=record_id, changed=True)


@router.post("/expenses", response_model=RecordCreated, status_code=201)
async def create_expense(request: ExpenseCreate) -> RecordCreated:

    """Record one recurring cost, which is an arrangement rather than a dated spend."""

    async with session_scope() as session:
        row = await records_repository.create_expense(
            session,
            user_id=request.user_id,
            label=request.label,
            amount=request.amount,
            frequency=request.frequency,
            category=request.category,
        )

        return RecordCreated(id=row.id, kind="expense")


@router.patch("/expenses/{record_id}", response_model=RecordChanged)
async def update_expense(record_id: str, request: ExpenseUpdate, user_id: int) -> RecordChanged:

    """Apply a partial change to a recurring cost this user owns."""

    async with session_scope() as session:
        changed = await records_repository.update_fields(
            session,
            ExpenseRecordRow,
            user_id,
            record_id,
            request.model_dump(exclude_unset=True),
        )

    if not changed:
        raise HTTPException(status_code=404, detail="no such record")

    return RecordChanged(id=record_id, changed=True)


@router.post("/liabilities", response_model=RecordCreated, status_code=201)
async def create_liability(request: LiabilityCreate) -> RecordCreated:

    """Record a debt, which has to exist before an EMI can be attached to it."""

    async with session_scope() as session:
        row = await records_repository.create_liability(
            session,
            user_id=request.user_id,
            label=request.label,
            principal_outstanding=request.principal_outstanding,
            interest_rate_percent=request.interest_rate_percent,
            tenure_months=request.tenure_months,
            lender=request.lender,
            opened_on=request.opened_on,
        )

        return RecordCreated(id=row.id, kind="liability")


@router.post("/emis", response_model=RecordCreated, status_code=201)
async def create_emi(request: EmiCreate) -> RecordCreated:

    """Record the payment servicing a liability, refusing when the caller does not own it."""

    async with session_scope() as session:
        row = await records_repository.create_emi(
            session,
            user_id=request.user_id,
            liability_id=request.liability_id,
            label=request.label,
            amount=request.amount,
            interest_rate_percent=request.interest_rate_percent,
            remaining_months=request.remaining_months,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="no such liability")

    return RecordCreated(id=row.id, kind="emi")


@router.post("/sips", response_model=RecordCreated, status_code=201)
async def create_sip(request: SipCreate) -> RecordCreated:

    """Record a standing instruction, which can only be changed later through the approval path."""

    async with session_scope() as session:
        row = await records_repository.create_sip(
            session,
            user_id=request.user_id,
            scheme_name=request.scheme_name,
            amount=request.amount,
            frequency=request.frequency,
            folio_id=request.folio_id,
            next_debit_on=request.next_debit_on,
            linked_goal_id=request.linked_goal_id,
        )

        return RecordCreated(id=row.id, kind="sip")


@router.post("/transactions", response_model=RecordCreated, status_code=201)
async def create_transaction(request: TransactionCreate) -> RecordCreated:

    """Record one dated spend, tagged with its import batch when it arrived from a statement."""

    async with session_scope() as session:
        row = await records_repository.create_transaction(
            session,
            user_id=request.user_id,
            occurred_on=request.occurred_on,
            amount=request.amount,
            category=request.category,
            merchant=request.merchant,
            description=request.description,
            import_batch_id=request.import_batch_id,
        )

        return RecordCreated(id=row.id, kind="transaction")


@router.post("/{kind}/{record_id}/archive", response_model=RecordChanged)
async def archive_record(kind: str, record_id: str, request: ArchiveRequest) -> RecordChanged:

    """Retire a record from future calculations while leaving it readable as history."""

    row_class = ARCHIVABLE.get(kind)

    if row_class is None:
        raise HTTPException(status_code=404, detail="no such record kind")

    async with session_scope() as session:
        changed = await records_repository.archive(session, row_class, request.user_id, record_id)

    if not changed:
        raise HTTPException(status_code=404, detail="no such record")

    return RecordChanged(id=record_id, changed=True)
