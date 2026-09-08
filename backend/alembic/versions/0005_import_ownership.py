"""Point the import tables at the users table, and create the rows they were already claiming.

Every record table has a foreign key to ``users``. ``document_imports``, ``staged_rows`` and
``import_templates`` had none, and the gap was not theoretical: identity in this phase is an integer
a client sends, nothing created the row it named, and so a person could upload a statement, watch it
extract and review a dozen staged rows before anything noticed. What noticed was a foreign key
violation at the commit - the one call that writes - with the whole transaction rolled back and the
review work lost.

The backfill runs before the constraints. Imports exist for ids that never had a user row, and those
imports are real work: a mapped statement, its staged rows, the file on disk. Deleting them to make
the constraint pass would be destroying data to satisfy a rule introduced afterwards, so this creates
the missing people instead and names them the way registration would.

``ON DELETE RESTRICT`` matches the record tables. Removing a person is not something this service
offers, and a cascade would make an import quietly disappear with them along with the audit trail of
what was read from it.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

OWNED = [
    ("document_imports", "user_id", "document_imports_user_id_fkey"),
    ("staged_rows", "user_id", "staged_rows_user_id_fkey"),
    ("import_templates", "created_by_user_id", "import_templates_created_by_user_id_fkey"),
]


def upgrade() -> None:

    """Create any user an import already claims, then make that claim a constraint."""

    for table, column, name in OWNED:

        op.execute(
            sa.text(
                f"""
                INSERT INTO users (id, display_name)
                SELECT DISTINCT t.{column}, 'User ' || t.{column}
                FROM {table} t
                LEFT JOIN users u ON u.id = t.{column}
                WHERE t.{column} IS NOT NULL AND u.id IS NULL
                ON CONFLICT (id) DO NOTHING
                """
            )
        )

        op.create_foreign_key(name, table, "users", [column], ["id"], ondelete="RESTRICT")


def downgrade() -> None:

    """Drop the constraints, leaving the backfilled people in place since nothing knows they were added."""

    for table, _, name in OWNED:
        op.drop_constraint(name, table, type_="foreignkey")
