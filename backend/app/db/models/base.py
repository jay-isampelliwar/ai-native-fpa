"""Column helpers and the mixin that every table model builds on."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Numeric, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column


MONEY = Numeric(14, 2)
RATE = Numeric(5, 2)


def db_enum(enum_class: type[StrEnum], name: str) -> ENUM:

    """Map a Python enum onto a Postgres enum type the migrations already created."""

    return ENUM(
        enum_class,
        name=name,
        create_type=False,
        values_callable=lambda members: [member.value for member in members],
        )


def created_at_column() -> Mapped[datetime]:

    """A timestamp the database fills in when the row is inserted."""

    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_column() -> Mapped[datetime]:

    """A timestamp the database fills in on insert and the app refreshes on every update."""

    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        )


class UserOwnedMixin:

    """The id, user_id and timestamp columns every table owned by one user starts with."""

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
