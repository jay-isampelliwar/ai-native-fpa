"""Steps every save tool shares: check required details, validate, save once per tool call, check the saved row, and return a typed result."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import PlannerContext
from app.agent.tools.operations import run_write
from app.agent.tools.results import ToolResult, checked, from_validation_error, invalid, to_message
from app.agent.tools.verify import confirm_saved
from app.db.models.base import UserOwnedMixin


type SaveAction[SchemaT] = Callable[[AsyncSession, int, SchemaT], Awaitable[UserOwnedMixin]]


def given_arguments(arguments: dict[str, Any]) -> dict[str, Any]:

    """Keep only the arguments the model filled in, leaving out the runtime."""

    return {name: value for name, value in arguments.items() if name != "runtime" and value is not None}


def missing_required(schema: type[BaseModel], given: dict[str, Any]) -> list[str]:

    """Name the required fields of the schema that the model did not fill in."""

    return [
        name.replace("_", " ")
        for name, field in schema.model_fields.items()
        if field.is_required() and name not in given
        ]


async def save_result[SchemaT: BaseModel](
    runtime: ToolRuntime[PlannerContext],
    schema: type[SchemaT],
    arguments: dict[str, Any],
    action: SaveAction[SchemaT],
    label: str,
    ) -> ToolResult:

    """Run one save: report missing required details, validate, save once for this tool call, check it, and return the saved fields with the new id."""

    given = given_arguments(arguments)

    missing = missing_required(schema, given)

    if missing:
        return invalid(
            "missing_fields",
            f"Required details missing for this {label}: {', '.join(missing)}.",
            {"missing": missing},
            )

    try:
        data = schema(**given)

    except ValidationError as exc:
        return from_validation_error(exc)

    async def save(session: AsyncSession) -> ToolResult:

        """Add the item in the guard's session, read it back to check every value, then commit it with this call's saved result."""

        record = await action(session, runtime.context.user_id, data)

        await confirm_saved(session, type(record), {"id": record.id}, data.model_dump(exclude_none=True))

        return checked(f"Saved {label}.", {"id": record.id, **data.model_dump(mode="json", exclude_none=True)})

    return await run_write(runtime, save)


async def save_record[SchemaT: BaseModel](
    runtime: ToolRuntime[PlannerContext],
    schema: type[SchemaT],
    arguments: dict[str, Any],
    action: SaveAction[SchemaT],
    label: str,
    ) -> ToolMessage:

    """Run one save and send its result back to the model."""

    result = await save_result(runtime, schema, arguments, action, label)

    return to_message(result, runtime.tool_call_id)
