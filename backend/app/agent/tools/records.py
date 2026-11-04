"""The memory tools: see what is missing, mark sections none or declined, and list, change or remove saved items."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_session
from app.agent.tools.operations import run_write
from app.agent.tools.results import ToolResult, from_record_error, from_validation_error, ok, to_message
from app.db.models.base import UserOwnedMixin
from app.features.coverage.schemas import CoverageChoice
from app.features.coverage.service import SECTIONS, CoverageService
from app.features.investments.market import MarketService
from app.features.records.exceptions import RecordError
from app.features.records.kinds import KINDS, RecordKind
from app.features.records.record_service import SYSTEM_COLUMNS, RecordService, check_fields


def show_value(value: Any) -> str:

    """Write one saved value the way a person would read it."""

    if isinstance(value, Enum):
        return str(value.value)

    if isinstance(value, Decimal):
        return format(value.normalize(), "f")

    if isinstance(value, date):
        return value.isoformat()

    return str(value)


def record_fields(record: UserOwnedMixin) -> dict[str, Any]:

    """One saved item as its id and its filled-in fields, each written the way a person would read it."""

    columns = [name for name in record.__table__.columns.keys() if name not in SYSTEM_COLUMNS]

    fields = {name: show_value(getattr(record, name)) for name in columns if getattr(record, name) is not None}

    return {"id": record.id, **fields}


@tool
async def get_missing_data(runtime: ToolRuntime[PlannerContext]) -> ToolMessage:

    """See which sections of the user's details are still not asked about, and which profile details are empty."""

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
async def update_data_coverage(
    runtime: ToolRuntime[PlannerContext],
    changes: Annotated[
        dict[str, CoverageChoice],
        f"Map of section to status. Sections: {', '.join(SECTIONS)}. "
        "none = the user has nothing in this section, declined = the user does not want to share it, "
        "pending = ask again later.",
        ],
    ) -> ToolMessage:

    """Remember that the user has none of something, or does not want to share it. Saving an item marks its section as provided by itself."""

    async def mark(session: AsyncSession) -> ToolResult:

        """Save the new section statuses in the guard's session."""

        statuses = await CoverageService(session).update(runtime.context.user_id, changes)

        return ok("Saved.", {"sections": {section: status.value for section, status in statuses.items()}})

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
    kind: Annotated[RecordKind, "Which kind of saved items to show."],
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

    """Show the user's saved items of one kind, each with its id, a page at a time. Use it to answer questions about them, and before adding, changing, removing or allocating."""

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

    return to_message(ok(message, data), runtime.tool_call_id)


@tool
async def update_record(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of item to change."],
    record_id: Annotated[int, "The id of the item, from list_records."],
    changes: Annotated[dict[str, Any], "Map of field name to its new value, only the fields the user asked to change."],
    ) -> ToolMessage:

    """Change some fields of one saved item. The same checks as when adding are run again."""

    async def change(session: AsyncSession) -> ToolResult:

        """Change the fields in the guard's session."""

        fields = await RecordService(session).update_record(runtime.context.user_id, kind, record_id, changes)

        changed = {name: show_value(value) for name, value in fields.items()}

        return ok(f"Updated {KINDS[kind].label} id {record_id}.", {"id": record_id, "changed": changed})

    return to_message(await run_write(runtime, change), runtime.tool_call_id)


@tool
async def delete_record(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of item to remove."],
    record_id: Annotated[int, "The id of the item, from list_records."],
    ) -> ToolMessage:

    """Remove one saved item. The app asks the user to approve this exact item before it runs."""

    async def remove(session: AsyncSession) -> ToolResult:

        """Remove the item in the guard's session, describing it before it is gone."""

        record = await RecordService(session).get_or_fail(runtime.context.user_id, kind, record_id)

        removed = record_fields(record)

        await RecordService(session).delete_record(runtime.context.user_id, kind, record_id)

        return ok(f"Removed {KINDS[kind].label}.", {"removed": removed})

    return to_message(await run_write(runtime, remove), runtime.tool_call_id)
