"""Add the loans and credit_cards tables that hold what the user owes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(14, 2)

RATE = sa.Numeric(5, 2)

LOAN_TYPE = postgresql.ENUM(
    "home",
    "car",
    "personal",
    "education",
    "gold",
    "other",
    name="loan_type",
    create_type=False,
)

TABLES = ("loans", "credit_cards")


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

    """Create the loan_type enum, then loans and credit_cards with a user_id index on each."""

    LOAN_TYPE.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "loans",
        *owner_columns(),
        sa.Column("loan_type", LOAN_TYPE, nullable=False),
        sa.Column("lender", sa.String(100), nullable=False),
        sa.Column("principal", MONEY, nullable=False),
        sa.Column("outstanding", MONEY, nullable=False),
        sa.Column("interest_rate", RATE, nullable=False),
        sa.Column("emi", MONEY, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("physical_asset_id", sa.BigInteger(), sa.ForeignKey("physical_assets.id"), nullable=True),
        *timestamp_columns(),
    )

    op.create_table(
        "credit_cards",
        *owner_columns(),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("credit_limit", MONEY, nullable=True),
        sa.Column("outstanding", MONEY, nullable=False, server_default="0"),
        sa.Column("due_day", sa.SmallInteger(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_credit_cards_due_day"),
    )

    for table in TABLES:
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:

    """Drop credit_cards and loans with their indexes, then the loan_type enum."""

    for table in reversed(TABLES):

        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_table(table)

    LOAN_TYPE.drop(op.get_bind(), checkfirst=False)
