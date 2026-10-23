"""Add the usage of each run to agent_runs: model and tool calls, input and output tokens, and their cost."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

COUNT_COLUMNS = ("model_calls", "tool_calls", "input_tokens", "output_tokens")


def upgrade() -> None:

    """Add the four counts, starting at zero, and the cost, empty when the model has no price."""

    for name in COUNT_COLUMNS:
        op.add_column("agent_runs", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))

    op.add_column("agent_runs", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))


def downgrade() -> None:

    """Drop the cost and the four counts."""

    op.drop_column("agent_runs", "cost_usd")

    for name in reversed(COUNT_COLUMNS):
        op.drop_column("agent_runs", name)
