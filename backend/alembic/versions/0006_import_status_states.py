"""Widen the import status constraint to the states the pipeline already sets.

``run_extraction`` sets ``needs_mapping`` for an unrecognised layout, but the check constraint
created in 0002 allows only five values and does not include it. Every unrecognised workbook
therefore failed on write rather than parking for a mapping, and the failure surfaced as a rolled
back transaction rather than as the state the client polls for.

``locked`` and ``rejected`` are added in the same change. A password protected PDF parks at
``locked`` until a password arrives, and a refused import is marked ``rejected`` rather than
deleted, so what was read and refused stays part of the import's history.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

OLD_STATES = "status IN ('uploaded','extracting','extracted','committed','failed')"

NEW_STATES = (
    "status IN ('uploaded','extracting','extracted','committed','failed','needs_mapping','locked','rejected')"
)


def upgrade() -> None:

    """Replace the status check with one that names every state the service can actually write."""

    op.drop_constraint("ck_document_imports_status", "document_imports", type_="check")

    op.create_check_constraint("ck_document_imports_status", "document_imports", NEW_STATES)


def downgrade() -> None:

    """Return to the original five states, failing if any row is parked in one of the new ones."""

    op.drop_constraint("ck_document_imports_status", "document_imports", type_="check")

    op.create_check_constraint("ck_document_imports_status", "document_imports", OLD_STATES)
