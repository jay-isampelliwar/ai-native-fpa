"""The shared queries for any table owned by one user: insert, find, list, get, update and delete."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.base import UserOwnedMixin


class BaseUserRecordRepository:

    """Queries that always filter by user_id, so one user can never touch another user's rows."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session the caller opened, so every method talks through it."""

        self.session = session

    async def insert[ModelT: UserOwnedMixin](
        self,
        model: type[ModelT],
        user_id: int,
        fields: dict[str, Any],
        ) -> ModelT:

        """Insert a row for the user and flush, so the database gives it an id."""

        record = model(user_id=user_id, **fields)

        self.session.add(record)

        await self.session.flush()

        return record

    async def find_match[ModelT: UserOwnedMixin](
        self,
        model: type[ModelT],
        user_id: int,
        match: dict[str, Any],
        ) -> ModelT | None:

        """Return the user's first row whose fields equal the given values, comparing text without case."""

        conditions = [model.user_id == user_id]

        for name, value in match.items():

            column = getattr(model, name)

            if type(value) is str:
                conditions.append(func.lower(column) == value.lower())

            else:
                conditions.append(column == value)

        query = select(model).where(*conditions).order_by(model.id).limit(1)

        return await self.session.scalar(query)

    async def list_page[ModelT: UserOwnedMixin](
        self,
        model: type[ModelT],
        user_id: int,
        filters: dict[str, Any],
        sort_by: str,
        descending: bool,
        offset: int,
        limit: int,
        ) -> tuple[Sequence[ModelT], int]:

        """Return one page of this user's rows matching the filters, in a stable order, and how many match in all."""

        conditions = [model.user_id == user_id, *(getattr(model, name) == value for name, value in filters.items())]

        total = await self.session.scalar(select(func.count()).select_from(model).where(*conditions))

        column = getattr(model, sort_by)
        order = (column.desc(), model.id.desc()) if descending else (column.asc(), model.id.asc())

        query = select(model).where(*conditions).order_by(*order).offset(offset).limit(limit)

        result = await self.session.scalars(query)

        return result.all(), total

    async def get_for_user[ModelT: UserOwnedMixin](
        self,
        model: type[ModelT],
        record_id: int,
        user_id: int,
        ) -> ModelT | None:

        """Return the row only when it exists and belongs to this user."""

        query = select(model).where(model.id == record_id, model.user_id == user_id)

        return await self.session.scalar(query)

    async def update_for_user[ModelT: UserOwnedMixin](
        self,
        model: type[ModelT],
        record_id: int,
        user_id: int,
        fields: dict[str, Any],
        ) -> ModelT | None:

        """Set the given fields on this user's row, with the owner in the UPDATE itself, or return None when the row is not theirs."""

        query = (
            update(model)
            .where(model.id == record_id, model.user_id == user_id)
            .values(**fields)
            .returning(model)
            )

        return await self.session.scalar(query)

    async def delete_for_user[ModelT: UserOwnedMixin](
        self,
        model: type[ModelT],
        record_id: int,
        user_id: int,
        ) -> bool:

        """Delete this user's row, with the owner in the DELETE itself, returning False when the row is not theirs."""

        query = (
            delete(model)
            .where(model.id == record_id, model.user_id == user_id)
            .returning(model.id)
            )

        return await self.session.scalar(query) is not None
