"""The database enum types, bound to the Python enums the domain already uses.

PostgreSQL enum types are created by the migration, not by SQLAlchemy. ``create_type=False``
says so: without it a test or a metadata create would try to create a type that already
exists and fail on a database that is perfectly correct.

``values_callable`` is the important detail. By default SQLAlchemy stores an enum member's
*name*, which for ``Frequency.MONTHLY`` is the uppercase ``MONTHLY``, while the column
accepts the lowercase ``monthly`` the schema declares. Mapping on value keeps the database
readable and keeps the Python side using the same strings the API and the seed data do.
"""

from sqlalchemy.dialects.postgresql import ENUM

from app.models.finance import ApprovalStatus, DepositKind, Frequency, HoldingKind, SipStatus


def pg_enum(python_enum: type, name: str) -> ENUM:

    """Bind a Python enum to an existing PostgreSQL type, storing values rather than member names."""

    return ENUM(
        python_enum,
        name=name,
        create_type=False,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


FREQUENCY = pg_enum(Frequency, "frequency")
SIP_STATUS = pg_enum(SipStatus, "sip_status")
DEPOSIT_KIND = pg_enum(DepositKind, "deposit_kind")
HOLDING_KIND = pg_enum(HoldingKind, "holding_kind")
APPROVAL_STATUS = pg_enum(ApprovalStatus, "approval_status")
