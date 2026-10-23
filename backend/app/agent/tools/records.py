"""The memory tools: see what is missing, mark sections none or declined, and list, change or remove saved items."""

import asyncio
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import PlannerContext
from app.agent.tools.limits import tool_session
from app.agent.tools.operations import run_write
from app.agent.tools.results import ToolResult, ok, to_message
from app.db.models.base import UserOwnedMixin
from app.features.coverage.schemas import CoverageChoice
from app.features.coverage.service import SECTIONS, CoverageService
from app.features.records.kinds import KINDS, RecordKind
from app.features.records.record_service import SYSTEM_COLUMNS, RecordService


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


@tool
async def list_records(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of saved items to show."],
    ) -> ToolMessage:

    """Show the user's saved items of one kind, each with its id. Use it to answer questions about them, and before changing, removing or allocating."""

    # TODO(orb-demo): remove this delay once the thinking pill has been checked.
    await asyncio.sleep(5)

    async with tool_session(runtime.context) as session:
        records = await RecordService(session).list_records(runtime.context.user_id, kind)

    label = KINDS[kind].label
    items = [record_fields(record) for record in records]

    if not items:
        return to_message(ok(f"No {label} saved.", {"kind": kind.value, "items": []}), runtime.tool_call_id)

    return to_message(ok(f"{len(items)} {label} saved.", {"kind": kind.value, "items": items}), runtime.tool_call_id)


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
