"""Add deleted_at to conversations so a deleted chat keeps its rows and records when it was removed."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:

    """Add a nullable deleted_at, empty for every chat that is not deleted."""

    op.add_column("conversations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:

    """Drop deleted_at."""

    op.drop_column("conversations", "deleted_at")
