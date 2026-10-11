"""Add password_hash to users so people can sign up and sign in with email and password."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:

    """Add a nullable password_hash, so users made before sign-up existed stay valid."""

    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))


def downgrade() -> None:

    """Drop password_hash."""

    op.drop_column("users", "password_hash")
