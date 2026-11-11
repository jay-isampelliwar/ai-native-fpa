"""Add the needs_password and needs_consent document states: a locked PDF, and pages only the model can read."""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

NEW_STATUSES = ("needs_password", "needs_consent")

OLD_STATUSES = ("uploaded", "needs_mapping", "parsed", "imported", "rejected", "failed")


def quoted(values: tuple[str, ...]) -> str:

    """Join status values into a quoted, comma separated SQL list."""

    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:

    """Add both values in their own commit, since Postgres cannot use a new enum value in the same transaction."""

    with op.get_context().autocommit_block():

        for status in NEW_STATUSES:
            op.execute(f"ALTER TYPE document_status ADD VALUE IF NOT EXISTS '{status}' AFTER 'needs_mapping'")


def downgrade() -> None:

    """Mark waiting documents failed, then rebuild the enum without the two values."""

    op.execute(f"UPDATE documents SET status = 'failed' WHERE status IN ({quoted(NEW_STATUSES)})")
    op.execute("ALTER TABLE documents ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE document_status RENAME TO document_status_old")
    op.execute(f"CREATE TYPE document_status AS ENUM ({quoted(OLD_STATUSES)})")
    op.execute("ALTER TABLE documents ALTER COLUMN status TYPE document_status USING status::text::document_status")
    op.execute("ALTER TABLE documents ALTER COLUMN status SET DEFAULT 'uploaded'")
    op.execute("DROP TYPE document_status_old")
