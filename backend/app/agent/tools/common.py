"""Steps every save tool shares: check required details, validate, save, and describe the result."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.tools import ToolRuntime
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import PlannerContext
from app.db.models.base import UserOwnedMixin
from app.db.session import SessionLocal
from app.features.records.exceptions import RecordError


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


def validation_message(exc: ValidationError) -> str:

    """Turn pydantic errors into one short line the model can repeat to the user."""

    problems = "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'details'}: {error['msg']}"
        for error in exc.errors()
        )

    return f"Not saved. {problems}"


def describe(data: BaseModel) -> str:

    """List the saved fields as name=value pairs."""

    return ", ".join(f"{name}={value}" for name, value in data.model_dump(exclude_none=True, mode="json").items())


async def save_record[SchemaT: BaseModel](
    runtime: ToolRuntime[PlannerContext],
    schema: type[SchemaT],
    arguments: dict[str, Any],
    action: SaveAction[SchemaT],
    label: str,
    ) -> str:

    """Run one save: report missing required details, validate, save for the signed-in user, and describe it."""

    given = given_arguments(arguments)

    missing = missing_required(schema, given)

    if missing:
        return f"Not saved. Required details missing for this {label}: {', '.join(missing)}."

    try:
        data = schema(**given)

    except ValidationError as exc:
        return validation_message(exc)

    try:

        async with SessionLocal() as session:
            record = await action(session, runtime.context.user_id, data)

    except RecordError as exc:
        return f"Not saved. {exc}"

    except IntegrityError:
        return f"Not saved. This {label} clashes with another saved item."

    return f"Saved {label} with id {record.id}: {describe(data)}."
