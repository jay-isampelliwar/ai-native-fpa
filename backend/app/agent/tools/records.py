"""The memory tools: see what is missing, mark sections none or declined, and list, change or remove saved items."""

import asyncio
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.agent.context import PlannerContext
from app.agent.tools.common import validation_message
from app.db.models.base import UserOwnedMixin
from app.db.session import SessionLocal
from app.features.coverage.schemas import CoverageChoice
from app.features.coverage.service import SECTIONS, CoverageService
from app.features.records.exceptions import RecordError
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


def show_record(record: UserOwnedMixin) -> str:

    """Write one saved item as its id followed by its filled-in fields."""

    columns = [name for name in record.__table__.columns.keys() if name not in SYSTEM_COLUMNS]

    fields = ", ".join(
        f"{name}={show_value(getattr(record, name))}" for name in columns if getattr(record, name) is not None
        )

    return f"id {record.id}: {fields}"


@tool
async def get_missing_data(runtime: ToolRuntime[PlannerContext]) -> str:

    """See which sections of the user's details are still not asked about, and which profile details are empty."""

    async with SessionLocal() as session:
        missing = await CoverageService(session).missing(runtime.context.user_id)

    if not missing.pending_sections and not missing.missing_profile_fields:
        return "Nothing is missing. Every section is provided, none or declined."

    lines = []

    if missing.pending_sections:
        lines.append(f"Sections not asked about yet: {', '.join(missing.pending_sections)}.")

    if missing.missing_profile_fields:
        lines.append(f"Profile details still empty: {', '.join(missing.missing_profile_fields)}.")

    return " ".join(lines)


@tool
async def update_data_coverage(
    runtime: ToolRuntime[PlannerContext],
    changes: Annotated[
        dict[str, CoverageChoice],
        f"Map of section to status. Sections: {', '.join(SECTIONS)}. "
        "none = the user has nothing in this section, declined = the user does not want to share it, "
        "pending = ask again later.",
        ],
    ) -> str:

    """Remember that the user has none of something, or does not want to share it. Saving an item marks its section as provided by itself."""

    try:

        async with SessionLocal() as session:
            statuses = await CoverageService(session).update(runtime.context.user_id, changes)

    except RecordError as exc:
        return f"Not saved. {exc}"

    details = ", ".join(f"{section}={status.value}" for section, status in statuses.items())

    return f"Saved: {details}."


@tool
async def list_records(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of saved items to show."],
    ) -> str:

    """Show the user's saved items of one kind, each with its id. Use it to answer questions about them, and before changing, removing or allocating."""

    # TODO(orb-demo): remove this delay once the thinking pill has been checked.
    await asyncio.sleep(5)

    async with SessionLocal() as session:
        records = await RecordService(session).list_records(runtime.context.user_id, kind)

    if not records:
        return f"No {KINDS[kind].label} saved."

    return "\n".join(show_record(record) for record in records)


@tool
async def update_record(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of item to change."],
    record_id: Annotated[int, "The id of the item, from list_records."],
    changes: Annotated[dict[str, Any], "Map of field name to its new value, only the fields the user asked to change."],
    ) -> str:

    """Change some fields of one saved item. The same checks as when adding are run again."""

    try:

        async with SessionLocal() as session:
            fields = await RecordService(session).update_record(runtime.context.user_id, kind, record_id, changes)

    except ValidationError as exc:
        return validation_message(exc)

    except RecordError as exc:
        return f"Not saved. {exc}"

    except IntegrityError:
        return "Not saved. This change clashes with another saved item."

    details = ", ".join(f"{name}={show_value(value)}" for name, value in fields.items())

    return f"Updated {KINDS[kind].label} id {record_id}: {details}."


@tool
async def delete_record(
    runtime: ToolRuntime[PlannerContext],
    kind: Annotated[RecordKind, "Which kind of item to remove."],
    record_id: Annotated[int, "The id of the item, from list_records."],
    ) -> str:

    """Remove one saved item. Only call this after the user clearly said yes to removing that exact item."""

    try:

        async with SessionLocal() as session:
            record = await RecordService(session).delete_record(runtime.context.user_id, kind, record_id)

    except RecordError as exc:
        return f"Not removed. {exc}"

    return f"Removed {KINDS[kind].label} {show_record(record)}."
