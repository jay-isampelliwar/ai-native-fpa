"""The memory tools: see what is missing, mark sections none or declined, and list, change or remove saved items."""

from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.blocks import records_block
from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_session
from app.agent.tools.operations import run_write
from app.agent.tools.results import ToolResult, checked, from_record_error, from_validation_error, ok, to_message
from app.agent.tools.verify import confirm_removed, confirm_saved, show_value
from app.db.models import DataCoverage
from app.db.models.base import UserOwnedMixin
from app.features.coverage.schemas import CoverageChoice
from app.features.coverage.service import SECTIONS, CoverageService
from app.features.investments.market import MarketService
from app.features.records.exceptions import RecordError
from app.features.records.kinds import KINDS, RecordKind
from app.features.records.record_service import SYSTEM_COLUMNS, RecordService, check_fields


def record_fields(record: UserOwnedMixin) -> dict[str, Any]:

    """One saved item as its id and its filled-in fields, each written the way a person would read it."""

    columns = [name for name in record.__table__.columns.keys() if name not in SYSTEM_COLUMNS]

    fields = {name: show_value(getattr(record, name)) for name in columns if getattr(record, name) is not None}

    return {"id": record.id, **fields}


@tool
async def get_missing_sections(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """List the sections (loans, insurance, goals and so on) the user has not told you about yet, and the empty profile details. Read-only. Use it to decide what to ask next."""

    async with tool_session(runtime.context) as session:
        missing = await CoverageService(session).missing(runtime.context.user_id)

    data = {
        "pending_sections": missing.pending_sections,
        "missing_profile_fields": missing.missing_profile_fields,
        }

    if not missing.pending_sections and not missing.missing_profile_fields:
        result = ok("Nothing is missing. Every section is provided, none or declined.", data)

    else:
        result = ok("Some details are still missing.", data)

    return to_message(result, runtime.tool_call_id)


@tool
async def mark_section_status(
    runtime: ToolRuntime[PlannerContext],
    changes: Annotated[
        dict[str, CoverageChoice],
        f"Map of section to status. Sections: {', '.join(SECTIONS)}. "
        "none = the user has nothing in this section, declined = the user does not want to share it, "
        "pending = ask again later.",
        ],
    ) -> ToolMessage:

    """Only for "I have no loans" or "I don't want to share my insurance": marks whole sections as none or declined. It never saves, changes or removes any item or amount. Saving an item marks its section as provided by itself."""

    async def mark(session: AsyncSession) -> ToolResult:

        """Save the new section statuses in the guard's session and read them back."""

        statuses = await CoverageService(session).update(runtime.context.user_id, changes)

        await confirm_saved(session, DataCoverage, {"user_id": runtime.context.user_id}, statuses)

        return checked("Saved.", {"sections": {section: status.value for section, status in statuses.items()}})

    return to_message(await run_write(runtime, mark), runtime.tool_call_id)


def chosen_fields(
    item: dict[str, Any],
    fields: list[str] | None,
    ) -> dict[str, Any]:

    """Keep only the asked-for fields of one item, always with its id."""

    if not fields:
        return item

    return {name: value for name, value in item.items() if name == "id" or name in fields}


def page_message(
    kind: RecordKind,
    shown: int,
    total: int,
    filtered: bool,
    ) -> str:

    """Say how many items this page shows out of how many match, naming the kind as the user would."""

    label = kind.value.replace("_", " ")

    if total == 0:
        return f"No {label} match these filters." if filtered else f"No {label} saved."

    return f"Showing {shown} of {total} {label}."


@tool
async def list_records(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of saved items to show, such as holdings for stocks and funds or bank_accounts."],
    page_size: Annotated[int | None, "How many items to return, 1 to 50. Default 20."] = None,
    cursor: Annotated[int | None, "next_cursor from an earlier list_records result, to get the next page."] = None,
    filters: Annotated[
        dict[str, Any] | None,
        'Only items whose fields equal these values, such as {"lender": "HDFC"}.',
        ] = None,
    sort: Annotated[
        str | None,
        'A field to sort by, smallest or oldest first. Put - in front for the largest first, such as "-amount".',
        ] = None,
    fields: Annotated[
        list[str] | None,
        "Only these fields of each item, to keep the answer short. The id always comes back.",
        ] = None,
    ) -> ToolMessage:

    """Read the user's saved items of one kind, each with its id, a page at a time. Read-only. Use it to answer any question about the user's own money, and to find an item's id before changing or removing it."""

    try:

        if fields:
            check_fields(kind, fields, "show")

        async with tool_session(runtime.context) as session:
            page = await RecordService(session).list_page(runtime.context.user_id, kind, page_size, cursor, filters, sort)

            named = await MarketService(session).describe_holdings(page.items) if kind == RecordKind.holdings else {}

    except ValidationError as exc:
        return to_message(from_validation_error(exc), runtime.tool_call_id)

    except RecordError as exc:
        return to_message(from_record_error(exc), runtime.tool_call_id)

    items = [chosen_fields({**record_fields(record), **named.get(record.id, {})}, fields) for record in page.items]

    data = {"kind": kind.value, "items": items, "total": page.total, "next_cursor": page.next_cursor}

    message = page_message(kind, len(items), page.total, bool(filters))

    block = records_block(kind, list(page.items), named, page.total)

    return to_message(ok(message, data, block), runtime.tool_call_id)


@tool
async def update_record(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of item to change."],
    record_id: Annotated[int, "The id of the item, from list_records."],
    changes: Annotated[
        dict[str, Any],
        "Map of field name to its new value, only the fields the user asked to change. "
        "For a holding saved as the wrong stock or fund, put the right isin here together with units and invested_amount.",
        ],
    ) -> ToolMessage:

    """Change some fields of one item that is already saved, such as an amount or a date, or move a holding to the right stock or fund by isin. Never use it to add a new item. The user approves the change on a card first, and the same checks as when adding run again."""

    async def change(session: AsyncSession) -> ToolResult:

        """Change the fields in the guard's session and read the item back to check them."""

        user_id = runtime.context.user_id

        fields = await RecordService(session).update_record(user_id, kind, record_id, changes)

        await confirm_saved(session, KINDS[kind].model, {"id": record_id, "user_id": user_id}, fields)

        changed = {name: show_value(value) for name, value in fields.items()}

        return checked(f"Updated {KINDS[kind].label} id {record_id}.", {"id": record_id, "changed": changed})

    return to_message(await run_write(runtime, change), runtime.tool_call_id)


@tool
async def delete_record(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of item to remove."],
    record_id: Annotated[int, "The id of the item, from list_records."],
    ) -> ToolMessage:

    """Remove one saved item for good, such as an expense that has stopped. The user approves this exact item on a card before it runs."""

    async def remove(session: AsyncSession) -> ToolResult:

        """Remove the item in the guard's session, describing it before it is gone, and check it is really gone."""

        user_id = runtime.context.user_id

        record = await RecordService(session).get_or_fail(user_id, kind, record_id)

        removed = record_fields(record)

        await RecordService(session).delete_record(user_id, kind, record_id)

        await confirm_removed(session, KINDS[kind].model, {"id": record_id, "user_id": user_id})

        return checked(f"Removed {KINDS[kind].label}.", {"removed": removed})

    return to_message(await run_write(runtime, remove), runtime.tool_call_id)
