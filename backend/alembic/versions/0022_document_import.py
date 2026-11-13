"""Add documents and import_rows: uploaded files and the full records parsed from them, held until the user approves."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

DOCUMENT_STATUS = postgresql.ENUM(
    "uploaded",
    "parsed",
    "imported",
    "rejected",
    "failed",
    name="document_status",
    create_type=False,
)

IMPORT_ROW_ACTION = postgresql.ENUM(
    "create",
    "update",
    "no_change",
    name="import_row_action",
    create_type=False,
)

IMPORT_ROW_STATUS = postgresql.ENUM(
    "proposed",
    "approved",
    "rejected",
    "written",
    "failed",
    "undone",
    name="import_row_status",
    create_type=False,
)

ENUMS = (DOCUMENT_STATUS, IMPORT_ROW_ACTION, IMPORT_ROW_STATUS)


def upgrade() -> None:

    """Create the three enum types, then documents and import_rows with their indexes."""

    for enum in ENUMS:
        enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("family", sa.String(100), nullable=True),
        sa.Column("status", DOCUMENT_STATUS, nullable=False, server_default="uploaded"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "sha256", name="uq_documents_user_sha256"),
    )

    op.create_index("ix_documents_user_status", "documents", ["user_id", "status"])

    op.create_table(
        "import_rows",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("target_table", sa.String(50), nullable=False),
        sa.Column("action", IMPORT_ROW_ACTION, nullable=True),
        sa.Column("status", IMPORT_ROW_STATUS, nullable=False, server_default="proposed"),
        sa.Column("parsed_data", postgresql.JSONB(), nullable=False),
        sa.Column("edited_data", postgresql.JSONB(), nullable=True),
        sa.Column("previous_data", postgresql.JSONB(), nullable=True),
        sa.Column("target_record_id", sa.BigInteger(), nullable=True),
        sa.Column("source", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("errors", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "row_number", name="uq_import_rows_document_row"),
    )

    op.create_index("ix_import_rows_document_status", "import_rows", ["document_id", "status"])
    op.create_index("ix_import_rows_user_id", "import_rows", ["user_id"])


def downgrade() -> None:

    """Drop import_rows and documents, then the three enum types."""

    op.drop_index("ix_import_rows_user_id", table_name="import_rows")
    op.drop_index("ix_import_rows_document_status", table_name="import_rows")
    op.drop_table("import_rows")

    op.drop_index("ix_documents_user_status", table_name="documents")
    op.drop_table("documents")

    for enum in reversed(ENUMS):
        enum.drop(op.get_bind(), checkfirst=False)
