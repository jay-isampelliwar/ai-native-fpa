"""Add the income_sources, expenses and transactions tables that monthly cash flow is worked out from."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(14, 2)

RATE = sa.Numeric(5, 2)

INCOME_SOURCE_TYPE = postgresql.ENUM(
    "salary",
    "rent",
    "business",
    "freelance",
    "pension",
    "other",
    name="income_source_type",
    create_type=False,
)

PAYMENT_FREQUENCY = postgresql.ENUM(
    "monthly",
    "quarterly",
    "half_yearly",
    "yearly",
    name="payment_frequency",
    create_type=False,
)

TRANSACTION_DIRECTION = postgresql.ENUM(
    "inflow",
    "outflow",
    name="transaction_direction",
    create_type=False,
)

EXPENSE_CATEGORY = postgresql.ENUM(
    "rent",
    "maintenance",
    "groceries",
    "electricity",
    "water",
    "gas",
    "mobile_internet",
    "fuel",
    "public_transport",
    "vehicle_maintenance",
    "education",
    "child_care",
    "elder_care",
    "medicines",
    "doctor_visits",
    "fitness",
    "smoking",
    "alcohol",
    "dining_out",
    "food_delivery",
    "clothing",
    "shopping",
    "electronics",
    "entertainment",
    "subscriptions",
    "travel",
    "household_help",
    "personal_care",
    "pets",
    "gifts",
    "donations",
    "family_support",
    "gambling",
    "other",
    name="expense_category",
    create_type=False,
)

TRANSACTION_CATEGORY = postgresql.ENUM(
    "bonus",
    "gift",
    "inheritance",
    "asset_sale",
    "refund",
    "purchase",
    "medical",
    "travel",
    "repair",
    "other",
    name="transaction_category",
    create_type=False,
)

ENUM_TYPES = (
    INCOME_SOURCE_TYPE,
    PAYMENT_FREQUENCY,
    TRANSACTION_DIRECTION,
    EXPENSE_CATEGORY,
    TRANSACTION_CATEGORY,
)

TABLES = ("income_sources", "expenses", "transactions")


def owner_columns() -> list[sa.Column]:

    """Fresh id and user_id columns that every table owned by one user starts with."""

    return [
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
    ]


def timestamp_columns() -> list[sa.Column]:

    """Fresh created_at and updated_at columns, both defaulting to now."""

    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:

    """Create the cash flow enum types, then the three tables and a user_id index on each."""

    bind = op.get_bind()

    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=False)

    op.create_table(
        "income_sources",
        *owner_columns(),
        sa.Column("source_type", INCOME_SOURCE_TYPE, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("frequency", PAYMENT_FREQUENCY, nullable=False, server_default="monthly"),
        sa.Column("yearly_growth_rate", RATE, nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        *timestamp_columns(),
    )

    op.create_table(
        "expenses",
        *owner_columns(),
        sa.Column("category", EXPENSE_CATEGORY, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("frequency", PAYMENT_FREQUENCY, nullable=False, server_default="monthly"),
        sa.Column("is_essential", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("end_date", sa.Date(), nullable=True),
        *timestamp_columns(),
    )

    op.create_table(
        "transactions",
        *owner_columns(),
        sa.Column("direction", TRANSACTION_DIRECTION, nullable=False),
        sa.Column("category", TRANSACTION_CATEGORY, nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamp_columns(),
    )

    for table in TABLES:
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:

    """Drop the three tables with their indexes, then the enum types."""

    for table in reversed(TABLES):

        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_table(table)

    bind = op.get_bind()

    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=False)
