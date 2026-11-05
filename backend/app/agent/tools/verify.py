"""The write check: read a saved row back from the database and refuse the save when it differs from what was asked."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class SaveMismatch(Exception):

    """The row read back after a save is missing or differs from what the tool asked to save."""

    def __init__(self, fields: dict[str, dict[str, str]]) -> None:

        """Keep each wrong field with the value asked for and the value found."""

        super().__init__("The saved row does not match what was asked.")

        self.fields = fields


def show_value(value: Any) -> str:

    """Write one saved value the way a person would read it."""

    if isinstance(value, Enum):
        return str(value.value)

    if isinstance(value, Decimal):
        return format(value.normalize(), "f")

    if isinstance(value, date):
        return value.isoformat()

    return str(value)


def same_value(
    saved: Any,
    expected: Any,
    ) -> bool:

    """True when the saved value equals the asked one, rounding the asked number half up to the column's decimal places like Postgres."""

    if isinstance(saved, Decimal) and isinstance(expected, (Decimal, int, float, str)):

        try:
            asked = Decimal(str(expected))

        except InvalidOperation:
            return False

        return asked.quantize(saved, rounding=ROUND_HALF_UP) == saved

    if isinstance(saved, Enum) or isinstance(expected, Enum):
        return show_value(saved) == show_value(expected)

    return saved == expected


def differences(
    row: Any,
    expected: dict[str, Any],
    ) -> dict[str, dict[str, str]]:

    """Every asked field of the row whose saved value differs, skipping names that are not columns of the row."""

    columns = set(row.__table__.columns.keys())
    wrong = {}

    for name, value in expected.items():

        if name not in columns:
            continue

        saved = getattr(row, name)

        if not same_value(saved, value):
            wrong[name] = {"asked": show_value(value), "saved": "not set" if saved is None else show_value(saved)}

    return wrong


async def read_back(
    session: AsyncSession,
    model: type,
    key: dict[str, Any],
    ) -> Any:

    """Read the row fresh from the database, not from the session's memory, after flushing pending changes."""

    query = select(model).execution_options(populate_existing=True)

    for name, value in key.items():
        query = query.where(getattr(model, name) == value)

    return await session.scalar(query)


async def confirm_saved(
    session: AsyncSession,
    model: type,
    key: dict[str, Any],
    expected: dict[str, Any],
    ) -> Any:

    """Return the saved row when it holds every asked value, otherwise raise so the whole save is undone."""

    row = await read_back(session, model, key)

    if row is None:
        raise SaveMismatch({"row": {"asked": "saved", "saved": "not found"}})

    wrong = differences(row, expected)

    if wrong:
        raise SaveMismatch(wrong)

    return row


async def confirm_removed(
    session: AsyncSession,
    model: type,
    key: dict[str, Any],
    ) -> None:

    """Raise so the removal is undone when the row can still be read."""

    if await read_back(session, model, key) is not None:
        raise SaveMismatch({"row": {"asked": "removed", "saved": "still there"}})
