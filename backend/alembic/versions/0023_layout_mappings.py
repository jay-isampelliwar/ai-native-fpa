"""Add layout_mappings for confirmed sheet shapes, a summary on documents, and the needs_mapping document state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

OLD_DOCUMENT_STATUSES = ("uploaded", "parsed", "imported", "rejected", "failed")


def quoted(values: tuple[str, ...]) -> str:

    """Join status values into a quoted, comma separated SQL list."""

    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:

    """Add the needs_mapping value in its own commit, then the summary column and layout_mappings."""

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'needs_mapping' AFTER 'uploaded'")

    op.add_column(
        "documents",
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "layout_mappings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("headers", postgresql.JSONB(), nullable=False),
        sa.Column("target_table", sa.String(50), nullable=True),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fingerprint", name="uq_layout_mappings_fingerprint"),
    )


def downgrade() -> None:

    """Drop layout_mappings and the summary column, mark waiting documents failed, then rebuild the enum without needs_mapping."""

    op.drop_table("layout_mappings")
    op.drop_column("documents", "summary")

    op.execute("UPDATE documents SET status = 'failed' WHERE status = 'needs_mapping'")
    op.execute("ALTER TABLE documents ALTER COLUMN status DROP DEFAULT")
    op.execute("DROP INDEX IF EXISTS ix_documents_user_status")
    op.execute("ALTER TYPE document_status RENAME TO document_status_old")
    op.execute(f"CREATE TYPE document_status AS ENUM ({quoted(OLD_DOCUMENT_STATUSES)})")
    op.execute(
        "ALTER TABLE documents ALTER COLUMN status TYPE document_status "
        "USING status::text::document_status"
    )
    op.execute("ALTER TABLE documents ALTER COLUMN status SET DEFAULT 'uploaded'")
    op.execute("DROP TYPE document_status_old")
    op.create_index("ix_documents_user_status", "documents", ["user_id", "status"])
