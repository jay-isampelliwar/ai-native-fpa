"""The declarative base and the column conventions every table in this service follows.

Two decisions are enforced here rather than remembered per table. Money is always
``NUMERIC(14, 2)`` mapped to ``Decimal``, and identifiers are always prefixed text. Both
exist to stop a class of bug at the type level: a float column would quietly defeat the
rounding policy in ``app.calculations.money``, and an integer primary key would mean the
``evidence_ids`` a skill quotes are not the keys anything is actually stored under.

``Money`` is an annotation, not a helper to call. Writing ``amount: Mapped[Money]`` on a
column gives it the right precision automatically, so a new table cannot get it wrong by
omission. ``Rate`` does the same for interest rates, which need more decimal places and
fewer whole digits.

``OwnedMixin`` carries ``user_id`` and its index. Every table holding user data uses it,
which is what makes "is this ownership scoped" answerable by looking at the class
declaration rather than by reading every query written against it.

The ORM models mirror ``docs/schema.sql`` rather than generating it. That file is the
initial migration and the reference a reviewer reads; these classes are how the
application talks to it. When the two disagree the migration wins, and a test asserts they
do not disagree.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Money = Annotated[Decimal, mapped_column(Numeric(14, 2))]
Rate = Annotated[Decimal, mapped_column(Numeric(6, 3))]
Units = Annotated[Decimal, mapped_column(Numeric(20, 6))]
RecordId = Annotated[str, mapped_column(String(64), primary_key=True)]


class Base(DeclarativeBase):

    """The declarative base every table inherits, carrying the shared column type conventions."""

    type_annotation_map = {
        Decimal: Numeric(14, 2),
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:

    """Adds creation and update timestamps written by the database rather than the application."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OwnedMixin:

    """Marks a table as holding user data, giving it the indexed owner column every read filters on."""

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


def owner_index(table_name: str, *columns: str) -> Index:

    """Build the composite index a table needs for its most common owner scoped query."""

    return Index(f"ix_{table_name}_owner_{'_'.join(columns)}", "user_id", *columns)
