"""Add questions and resolved to import_rows: the doubts the user must answer, and the matched records and ids."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:

    """Add both JSON columns, empty for every existing row."""

    op.add_column(
        "import_rows",
        sa.Column("questions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "import_rows",
        sa.Column("resolved", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:

    """Drop both columns."""

    op.drop_column("import_rows", "resolved")
    op.drop_column("import_rows", "questions")
