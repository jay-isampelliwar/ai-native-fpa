"""Add the users and family_members tables that every financial table hangs off."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

RISK_APPETITE = postgresql.ENUM(
    "low",
    "medium",
    "high",
    name="risk_appetite",
    create_type=False,
)

FAMILY_RELATION = postgresql.ENUM(
    "spouse",
    "child",
    "parent",
    "sibling",
    "other",
    name="family_relation",
    create_type=False,
)

ENUM_TYPES = (RISK_APPETITE, FAMILY_RELATION)


def timestamp_columns() -> list[sa.Column]:

    """Fresh created_at and updated_at columns, both defaulting to now."""

    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:

    """Create the two enum types, then users and the family members that belong to them."""

    bind = op.get_bind()

    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=False)

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("risk_appetite", RISK_APPETITE, nullable=True),
        sa.Column("retirement_age", sa.SmallInteger(), nullable=True),
        sa.Column("life_expectancy", sa.SmallInteger(), nullable=False, server_default="85"),
        *timestamp_columns(),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "family_members",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("relation", FAMILY_RELATION, nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("is_dependent", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamp_columns(),
    )

    op.create_index("ix_family_members_user_id", "family_members", ["user_id"])


def downgrade() -> None:

    """Drop family_members, then users, then the enum types nothing references any more."""

    op.drop_index("ix_family_members_user_id", table_name="family_members")
    op.drop_table("family_members")
    op.drop_table("users")

    bind = op.get_bind()

    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=False)
