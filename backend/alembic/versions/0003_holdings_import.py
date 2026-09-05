"""Widen holdings to the common import model, and add template and provenance tables.

Three real statements drove every column here. Two of the three carry no ISIN at all, so identity
cannot be assumed to be an ISIN even though it is preferred - ``identifier_type`` records what a row
was actually matched on, and a holding identified by scheme name is honestly worse evidence than one
identified by ISIN rather than silently equivalent.

One statement gives invested and current value per row; another gives only quantity and two prices
and expects the reader to multiply. Both are stored as values, computed at extraction time where
they were absent, because a downstream query should not have to know which broker a row came from.

``import_templates`` is what makes an unknown file a one time problem. A fingerprint of the sheet
names and header cells maps to a confirmed column mapping, so the second file of a given shape is
parsed deterministically by the mapping a person already approved for the first.

``staged_rows`` gains the sheet name, row number and the raw cells it came from. Reconciling a total
that is off by one row means going back to the source line, and a payload alone cannot say which
line of which sheet produced it.

``document_imports`` gains the statement's own totals beside the ones computed from the rows. A
statement that says its portfolio is worth one figure and whose rows add to another has a problem
worth stopping on, and storing both is what makes that checkable after the fact.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:

    """Widen holdings, add the template registry, and record where every staged row came from."""

    op.add_column("holdings", sa.Column("account_label", sa.Text(), nullable=True))
    op.add_column("holdings", sa.Column("asset_type", sa.Text(), nullable=True))
    op.add_column("holdings", sa.Column("identifier_type", sa.Text(), nullable=False, server_default="symbol"))
    op.add_column("holdings", sa.Column("invested_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("holdings", sa.Column("current_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("holdings", sa.Column("last_price", sa.Numeric(14, 4), nullable=True))
    op.add_column("holdings", sa.Column("source", sa.Text(), nullable=True))
    op.add_column("holdings", sa.Column("import_batch_id", sa.Text(), nullable=True))

    op.create_index("ix_holdings_user_isin", "holdings", ["user_id", "isin"])

    op.create_table(
        "import_templates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("document_kind", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False, unique=True),
        sa.Column("sheet_name", sa.Text(), nullable=True),
        sa.Column("header_row", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_data_row", sa.Integer(), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=False),
        sa.Column("totals_locator", postgresql.JSONB(), nullable=True),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_import_templates_provider", "import_templates", ["provider"])

    op.add_column("staged_rows", sa.Column("source_sheet", sa.Text(), nullable=True))
    op.add_column("staged_rows", sa.Column("source_row_number", sa.Integer(), nullable=True))
    op.add_column("staged_rows", sa.Column("source_cells", postgresql.JSONB(), nullable=True))

    op.add_column("document_imports", sa.Column("template_id", sa.String(64), nullable=True))
    op.add_column("document_imports", sa.Column("statement_totals", postgresql.JSONB(), nullable=True))
    op.add_column("document_imports", sa.Column("computed_totals", postgresql.JSONB(), nullable=True))
    op.add_column("document_imports", sa.Column("reconciled", sa.Boolean(), nullable=True))
    op.add_column("document_imports", sa.Column("reconciliation_note", sa.Text(), nullable=True))
    op.add_column("document_imports", sa.Column("proposed_mapping", postgresql.JSONB(), nullable=True))

    op.drop_constraint("ck_document_imports_status", "document_imports", type_="check")

    op.create_check_constraint(
        "ck_document_imports_status",
        "document_imports",
        "status IN ('uploaded','extracting','needs_mapping','extracted','committed','failed')",
    )


def downgrade() -> None:

    """Reverse every addition, restoring the narrower status set last so nothing violates it."""

    op.execute("UPDATE document_imports SET status = 'failed' WHERE status = 'needs_mapping'")

    op.drop_constraint("ck_document_imports_status", "document_imports", type_="check")

    op.create_check_constraint(
        "ck_document_imports_status",
        "document_imports",
        "status IN ('uploaded','extracting','extracted','committed','failed')",
    )

    for column in ("proposed_mapping", "reconciliation_note", "reconciled", "computed_totals", "statement_totals", "template_id"):
        op.drop_column("document_imports", column)

    for column in ("source_cells", "source_row_number", "source_sheet"):
        op.drop_column("staged_rows", column)

    op.drop_index("ix_import_templates_provider", table_name="import_templates")
    op.drop_table("import_templates")

    op.drop_index("ix_holdings_user_isin", table_name="holdings")

    for column in ("import_batch_id", "source", "last_price", "current_value", "invested_value", "identifier_type", "asset_type", "account_label"):
        op.drop_column("holdings", column)
