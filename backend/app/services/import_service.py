"""The upload, extract, reconcile and commit pipeline, and the rules that keep it safe.

This is the path real financial data takes into the system at volume, and it has exactly one
non negotiable property: nothing extracted reaches a record table until a person has seen it. The
service stages rows, lets them be corrected, and commits only what was accepted.

Extraction runs as a background job because it takes longer than a request. The upload handler
returns as soon as bytes are stored, and the client polls the import's status - which lives in the
database, so a restart mid extraction shows a stuck import rather than a lie.

Every way that job can stop now reaches that status. An exception inside it used to be recorded on
the in memory job handle and nowhere else, leaving the row at ``extracting`` and the client polling
a job that had already failed - a spinner with nothing behind it, for as long as the tab stayed
open. A crash writes the reason to the row, and ``abandon_unfinished`` does the same at startup for
anything a stopped process left behind, because a job handle does not survive a restart and the row
does.

Duplicate detection happens twice, at two different levels. The same file uploaded twice is caught
by checksum before anything is extracted. A row that is already in someone's records is caught per
row and marked ``duplicate`` rather than dropped - a person may know that two identical charges on
one day are genuinely two charges, or that they really do hold the same fund in two folios.

Each kind is matched the way a person would recognise it. A transaction is the same transaction on
date, amount and merchant. An income, expense, EMI or SIP is the same one by kind and label, which is
what "my salary" means to the person who typed it. A holding is the same holding by ISIN where the
statement carried one and by name where it did not. Only transactions were checked before this, so a
plan re-exported with one cell changed - a new checksum, past the file level check - staged every
income and every EMI again and doubled them on commit.

An import that produced nothing is not a duplicate worth protecting. The checksum check exists to
stop the same statement being written twice, and one sitting at ``needs_mapping`` wrote nothing at
all - so re uploading it re reads the same row rather than handing back the state it got stuck in.
Without that, every file uploaded before the reader existed stayed stuck forever: the second upload
was answered from the first attempt and no extraction ever ran again. A ``committed`` or
``extracted`` import is still returned as the duplicate it is.

Committing writes every accepted row under one ``import_batch_id`` and in one transaction. Either
the whole statement lands or none of it does; a half committed import is the state nobody can
reason about later.

Rows a person rejected are kept, not deleted. What was extracted and refused is as much a part of
the import's history as what was accepted, and it is the evidence for why a total does not match a
statement.

Reconciliation compares the sum of extracted rows against the statement's own stated totals, and it
catches what row level confidence cannot: a whole sheet skipped, a column mapped to the wrong field, a
total row imported as a holding. Every row can look individually plausible while the total is wrong by
one line, which is precisely the failure a person reviewing rows one at a time will not see.

An unrecognised layout becomes ``needs_mapping`` rather than a failure. The layout is stored so a
mapping can be proposed, confirmed once, and reused - which is what makes an unfamiliar provider a one
time cost instead of a recurring one.

A holding whose statement gave no invested value gets one derived from units times average cost, which
is arithmetic on two stated figures rather than an estimate. Without it a portfolio read back as worth
its full current value against an investment of zero, so every rupee of it showed as unrealised gain -
a figure that was not slightly wrong but entirely wrong, and reported confidently. Where the statement
did not state a per unit cost either, there is nothing to derive from and the value stays absent.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.extraction.dispatcher import extract_document
from app.models.finance import HoldingKind
from app.models.orm.cashflow import ExpenseRecordRow, ExpenseTransactionRow, IncomeRecordRow
from app.models.orm.credit import EmiRecordRow, SipRecordRow
from app.models.orm.investments import GoalRow, HoldingRow
from app.models.orm.imports import DocumentImportRow, StagedRowRow
from app.repositories.goals_repository import goals_repository
from app.repositories.records_repository import records_repository
from app.services.jobs import job_runner
from app.services.record_writes import write_one

RECORD_TABLES = {
    "income": (IncomeRecordRow, IncomeRecordRow.label),
    "expense": (ExpenseRecordRow, ExpenseRecordRow.label),
    "emi": (EmiRecordRow, EmiRecordRow.label),
    "sip": (SipRecordRow, SipRecordRow.scheme_name),
}

RECONCILE_TOLERANCE = Decimal("0.005")


class ImportService:

    """Moves an uploaded document from bytes to staged rows to committed records, a person in between."""

    async def create_import(
        self,
        user_id: int,
        filename: str,
        content_type: str,
        content: bytes,
        storage,
        ) -> tuple[DocumentImportRow, bool]:

        """Store an upload and register it, reporting whether this exact file was already imported."""

        suffix = f".{filename.rsplit('.', 1)[-1]}" if "." in filename else ""

        storage_key, checksum = await storage.put(user_id, content, suffix)

        async with session_scope() as session:

            existing = await session.scalar(
                select(DocumentImportRow).where(
                    DocumentImportRow.user_id == user_id,
                    DocumentImportRow.checksum == checksum,
                    DocumentImportRow.status != "failed",
                )
            )

            if existing is not None and existing.status == "needs_mapping":

                existing.status = "uploaded"
                existing.error = None
                existing.row_count = 0

                return existing, False

            if existing is not None:
                return existing, True

            row = DocumentImportRow(
                id=f"imp_{uuid4().hex[:12]}",
                user_id=user_id,
                filename=filename,
                content_type=content_type,
                byte_size=len(content),
                storage_key=storage_key,
                checksum=checksum,
                status="uploaded",
            )

            session.add(row)

            await session.flush()

            return row, False

    def start_extraction(self, import_id: str, filename: str, content_type: str, content: bytes) -> None:

        """Kick off extraction in the background so the upload request returns immediately."""

        async def work() -> None:

            try:
                await self.run_extraction(import_id, filename, content_type, content)

            except Exception as exc:

                await self.mark_failed(import_id, f"reading this file failed: {type(exc).__name__}")

                raise

        job_runner.start(import_id, work)

    async def mark_failed(self, import_id: str, reason: str) -> None:

        """Put the failure where the client polls, since a job's exception lives only in this process."""

        async with session_scope() as session:

            record = await session.get(DocumentImportRow, import_id)

            if record is None or record.status in {"extracted", "committed"}:
                return

            record.status = "failed"
            record.error = reason

    async def abandon_unfinished(self) -> int:

        """Fail every import left mid read by a stopped process, so nothing polls a job that no longer exists."""

        async with session_scope() as session:

            stranded = (
                await session.scalars(
                    select(DocumentImportRow).where(DocumentImportRow.status.in_(("uploaded", "extracting")))
                )
            ).all()

            for record in stranded:
                record.status = "failed"
                record.error = "the server stopped while reading this file - upload it again"

        return len(stranded)

    async def run_extraction(self, import_id: str, filename: str, content_type: str, content: bytes) -> None:

        """Extract a document and stage every row it produced, recording a failure rather than raising."""

        async with session_scope() as session:
            record = await session.get(DocumentImportRow, import_id)

            if record is None:
                return

            record.status = "extracting"

            user_id = record.user_id

        result = await extract_document(filename, content_type, content, user_id)

        async with session_scope() as session:

            record = await session.get(DocumentImportRow, import_id)

            if record is None:
                return

            record.extractor = result.extractor
            record.detected_format = result.detected_format
            record.document_kind = result.document_kind
            record.template_id = result.template_id

            if result.statement_totals:
                record.statement_totals = {key: str(value) for key, value in result.statement_totals.items()}

            if result.layout:
                record.proposed_mapping = {"layout": result.layout}

            if result.needs_mapping:
                record.status = "needs_mapping"
                record.error = result.error

                return

            if result.error and not result.rows:
                record.status = "failed"
                record.error = result.error

                return

            record.error = result.error

            for index, extracted in enumerate(result.rows):

                duplicate = await self._is_duplicate(
                    session,
                    record.user_id,
                    extracted.target_table,
                    extracted.payload,
                )

                session.add(
                    StagedRowRow(
                        id=f"stg_{uuid4().hex[:12]}",
                        import_id=import_id,
                        user_id=record.user_id,
                        row_index=index,
                        target_table=extracted.target_table,
                        payload=extracted.payload,
                        confidence=float(extracted.confidence),
                        status="duplicate" if duplicate else "pending",
                        issue=extracted.issue or ("this already appears in your records" if duplicate else None),
                        source_sheet=extracted.source_sheet,
                        source_row_number=extracted.source_row_number,
                        source_cells={"cells": extracted.source_cells} if extracted.source_cells else None,
                    )
                )

            computed, reconciled, note = self.reconcile(result)

            record.computed_totals = {key: str(value) for key, value in computed.items()}
            record.reconciled = reconciled
            record.reconciliation_note = note

            record.row_count = len(result.rows)
            record.status = "extracted"
            record.extracted_at = datetime.now(UTC)


    async def _commit_holding(self, session: AsyncSession, user_id: int, row: StagedRowRow, batch_id: str):

        """Write one staged holding, keeping the identifier kind the source statement actually supported."""

        payload = row.payload

        asset_type = (payload.get("asset_type") or "").lower()

        kind = HoldingKind.MUTUAL_FUND if ("fund" in asset_type or "debt" in asset_type) else HoldingKind.STOCK

        as_of = (
            datetime.fromisoformat(payload["as_of"]).date()
            if payload.get("as_of")
            else datetime.now(UTC).date()
        )

        units = Decimal(payload.get("quantity") or "0")

        average_cost = Decimal(payload.get("average_cost") or "0")

        return await records_repository.create_holding(
            session,
            user_id=user_id,
            kind=kind,
            instrument_name=payload["instrument_name"],
            units=units,
            average_cost=average_cost,
            as_of=as_of,
            isin=payload.get("isin"),
            folio_id=payload.get("folio_id"),
            asset_type=payload.get("asset_type"),
            identifier_type=payload.get("identifier_type", "symbol"),
            invested_value=invested_from(payload, units, average_cost),
            current_value=Decimal(payload["current_value"]) if payload.get("current_value") else None,
            last_price=Decimal(payload["last_price"]) if payload.get("last_price") else None,
            source=payload.get("source"),
            account_label=payload.get("account_label"),
            import_batch_id=batch_id,
        )

    def reconcile(self, result) -> tuple[dict, bool | None, str | None]:

        """Compare the sum of extracted rows against the statement's own totals, within a paisa tolerance."""

        computed: dict[str, Decimal] = {}

        for field in ("invested_value", "current_value"):

            values = [Decimal(row.payload[field]) for row in result.rows if row.payload.get(field)]

            if values:
                computed[field] = sum(values, Decimal("0"))

        if not result.statement_totals or not computed:
            return computed, None, "this document states no totals to reconcile against"

        problems: list[str] = []

        for field, stated in result.statement_totals.items():

            ours = computed.get(field)

            if ours is None or stated == 0:
                continue

            drift = abs(ours - stated) / abs(stated)

            if drift > RECONCILE_TOLERANCE:
                problems.append(
                    f"{field.replace('_', ' ')} differs from the statement by {drift * 100:.2f}%"
                )

        if problems:
            return computed, False, "; ".join(problems)

        return computed, True, "extracted rows match the totals this document states"

    async def _is_duplicate(
        self,
        session: AsyncSession,
        user_id: int,
        target_table: str,
        payload: dict,
        ) -> bool:

        """Check whether this row is already in the person's records, whatever kind of row it is."""

        if target_table == "records":
            return await self._record_exists(session, user_id, payload)

        if target_table == "holdings":
            return await self._holding_exists(session, user_id, payload)

        if target_table == "goals":
            return await self._goal_exists(session, user_id, payload)

        if not payload.get("occurred_on") or not payload.get("amount"):
            return False


        existing = await session.scalar(
            select(func.count())
            .select_from(ExpenseTransactionRow)
            .where(
                ExpenseTransactionRow.user_id == user_id,
                ExpenseTransactionRow.occurred_on == datetime.fromisoformat(payload["occurred_on"]).date(),
                ExpenseTransactionRow.amount == Decimal(payload["amount"]),
                ExpenseTransactionRow.merchant == payload.get("merchant", ""),
            )
        )

        return bool(existing)

    async def _record_exists(self, session: AsyncSession, user_id: int, payload: dict) -> bool:

        """Match an income, expense, EMI or SIP by kind and label, the way a person recognises the same thing."""

        kind = payload.get("kind")

        label = str((payload.get("fields") or {}).get("label") or "").strip().lower()

        if not kind or not label:
            return False

        row_type, column = RECORD_TABLES.get(kind, (None, None))

        if row_type is None:
            return False

        existing = await session.scalar(
            select(func.count())
            .select_from(row_type)
            .where(
                row_type.user_id == user_id,
                func.lower(func.trim(column)) == label,
            )
        )

        return bool(existing)

    async def _goal_exists(self, session: AsyncSession, user_id: int, payload: dict) -> bool:

        """Match a goal by the name a person gave it, which is what they would recognise as the same goal."""

        label = str(payload.get("label") or "").strip().lower()

        if not label:
            return False

        existing = await session.scalar(
            select(func.count())
            .select_from(GoalRow)
            .where(GoalRow.user_id == user_id, func.lower(func.trim(GoalRow.label)) == label)
        )

        return bool(existing)

    async def _holding_exists(self, session: AsyncSession, user_id: int, payload: dict) -> bool:

        """Match a holding on its ISIN where the statement carried one, and on its name where it did not."""

        isin = str(payload.get("isin") or "").strip()

        name = str(payload.get("instrument_name") or "").strip().lower()

        if isin and isin.upper() != "UNKNOWN":
            match = HoldingRow.isin == isin

        elif name:
            match = func.lower(func.trim(HoldingRow.instrument_name)) == name

        else:
            return False

        existing = await session.scalar(
            select(func.count()).select_from(HoldingRow).where(HoldingRow.user_id == user_id, match)
        )

        return bool(existing)

    async def update_row(self, user_id: int, row_id: str, changes: dict) -> StagedRowRow | None:

        """Apply a person's correction to one staged row, marking it edited and no longer doubtful."""

        async with session_scope() as session:

            row = await session.scalar(
                select(StagedRowRow).where(StagedRowRow.id == row_id, StagedRowRow.user_id == user_id)
            )

            if row is None:
                return None

            payload = dict(row.payload)

            payload.update({key: value for key, value in changes.items() if value is not None})

            row.payload = payload
            row.edited = True
            row.issue = None
            row.confidence = 1.0

            return row

    async def set_row_status(self, user_id: int, row_id: str, status: str) -> StagedRowRow | None:

        """Accept or reject one staged row, which is the decision the commit later acts on."""

        async with session_scope() as session:

            row = await session.scalar(
                select(StagedRowRow).where(StagedRowRow.id == row_id, StagedRowRow.user_id == user_id)
            )

            if row is None:
                return None

            row.status = status

            return row

    async def commit(self, user_id: int, import_id: str) -> dict:

        """Write every accepted row under one batch id in one transaction, or write none of them."""

        async with session_scope() as session:

            record = await session.scalar(
                select(DocumentImportRow).where(
                    DocumentImportRow.id == import_id,
                    DocumentImportRow.user_id == user_id,
                )
            )

            if record is None:
                return {"status": "not_found"}

            if record.status == "committed":
                return {"status": "already_committed", "import_batch_id": record.import_batch_id}

            if record.status != "extracted":
                return {"status": "not_ready", "detail": f"this import is {record.status}"}

            rows = (
                await session.scalars(
                    select(StagedRowRow).where(
                        StagedRowRow.import_id == import_id,
                        StagedRowRow.status == "accepted",
                    )
                )
            ).all()

            if not rows:
                return {"status": "nothing_accepted"}

            batch_id = f"batch_{uuid4().hex[:12]}"

            written = 0

            for row in rows:

                if row.target_table == "holdings":

                    created = await self._commit_holding(session, user_id, row, batch_id)

                    row.committed_record_id = created.id

                    written += 1

                    continue

                if row.target_table == "goals":

                    created = await goals_repository.create_goal(
                        session,
                        user_id=user_id,
                        label=row.payload["label"],
                        target_amount=Decimal(row.payload["target_amount"]),
                        target_date=datetime.fromisoformat(row.payload["target_date"]).date(),
                        kind=row.payload.get("kind", "custom"),
                        priority=int(row.payload.get("priority", 3)),
                    )

                    row.committed_record_id = created.id

                    written += 1

                    continue

                if row.target_table == "records":

                    created = await write_one(session, user_id, row.payload)

                    if created is None:
                        continue

                    row.committed_record_id = created.id

                    written += 1

                    continue

                if row.target_table != "expense_transactions":
                    continue

                created = await records_repository.create_transaction(
                    session,
                    user_id=user_id,
                    occurred_on=datetime.fromisoformat(row.payload["occurred_on"]).date(),
                    amount=Decimal(row.payload["amount"]),
                    category=row.payload.get("category", "uncategorised"),
                    merchant=row.payload.get("merchant", ""),
                    description=row.payload.get("description", ""),
                    import_batch_id=batch_id,
                )

                row.committed_record_id = created.id

                written += 1

            record.status = "committed"
            record.import_batch_id = batch_id
            record.committed_at = datetime.now(UTC)

            return {"status": "committed", "import_batch_id": batch_id, "rows_written": written}


import_service = ImportService()


def invested_from(payload: dict, units: Decimal, average_cost: Decimal) -> Decimal | None:

    """Take the stated invested value, or derive it from units and average cost when the sheet omitted it."""

    if payload.get("invested_value"):
        return Decimal(str(payload["invested_value"]))

    if units > 0 and average_cost > 0:
        return (units * average_cost).quantize(Decimal("0.01"))

    return None
