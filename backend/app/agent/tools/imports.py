"""The tools that let the planner talk about an uploaded document without ever being shown the file."""

from langchain_core.tools import tool

from app.services.import_service import import_service

SAMPLE_LIMIT = 3

CERTAIN_ENOUGH = 0.9

LABEL_KEYS = ("merchant", "label", "scheme_name", "name", "description")

AMOUNT_KEYS = ("amount", "target_amount", "current_value", "invested_value", "monthly_amount")

DATE_KEYS = ("occurred_on", "target_date", "as_of", "started_on")

PENDING_STATUSES = ("uploaded", "extracting", "extracted", "locked", "needs_mapping")


def first_value(payload: dict, keys: tuple[str, ...]) -> str | None:

    """Take whichever of these fields this row happens to carry, since one payload shape per table."""

    for key in keys:

        value = payload.get(key)

        if value:
            return str(value)

    return None


def describe_row(row) -> dict:

    """Reduce one staged row to the few fields a sentence about it needs, never the whole payload."""

    return {
        "kind": row.target_table,
        "label": first_value(row.payload, LABEL_KEYS),
        "amount": first_value(row.payload, AMOUNT_KEYS),
        "date": first_value(row.payload, DATE_KEYS),
        "confidence": float(row.confidence),
        "issue": row.issue,
        "source": f"{row.source_sheet} row {row.source_row_number}" if row.source_sheet else None,
    }


@tool("read_import_summary")
async def read_import_summary(user_id: int, import_id: str) -> dict:

    """Report what was read from one uploaded document, so it can be described before anyone approves it."""

    record = await import_service.get_import(user_id, import_id)

    if record is None:
        return {"note": "there is no such document"}

    if record.status != "extracted":
        return {
            "filename": record.filename,
            "status": record.status,
            "note": record.error or f"this document is {record.status}",
        }

    rows = await import_service.list_rows(user_id, import_id)

    pending = [row for row in rows if row.status == "pending"]
    duplicates = [row for row in rows if row.status == "duplicate"]

    uncertain = [row for row in pending if float(row.confidence) < CERTAIN_ENOUGH or row.issue]

    doubtful = sorted(uncertain, key=lambda row: row.confidence)[:SAMPLE_LIMIT]

    kinds: dict[str, int] = {}

    for row in pending:
        kinds[row.target_table] = kinds.get(row.target_table, 0) + 1

    return {
        "filename": record.filename,
        "status": record.status,
        "document_kind": record.document_kind,
        "new_rows": len(pending),
        "rows_by_kind": kinds,
        "duplicate_rows": len(duplicates),
        "duplicate_examples": [describe_row(row) for row in duplicates[:SAMPLE_LIMIT]],
        "least_certain": [describe_row(row) for row in doubtful],
        "statement_totals": record.statement_totals,
        "computed_totals": record.computed_totals,
        "reconciled": record.reconciled,
        "reconciliation_note": record.reconciliation_note,
    }


@tool("list_pending_imports")
async def list_pending_imports(user_id: int) -> dict:

    """List the documents this person has uploaded that are still waiting on them for something."""

    records = await import_service.list_pending(user_id)

    waiting = [record for record in records if record.status in PENDING_STATUSES]

    if not waiting:
        return {"documents": [], "note": "nothing is waiting to be reviewed"}

    return {
        "documents": [
            {
                "import_id": record.id,
                "filename": record.filename,
                "status": record.status,
                "rows_found": record.row_count,
                "note": record.error,
            }
            for record in waiting
        ]
    }


IMPORT_TOOLS = [
    read_import_summary,
    list_pending_imports,
]
