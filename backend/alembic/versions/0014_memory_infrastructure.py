"""Add outbox_events, memory_items and memory_events for deferred memory work through Redis Streams."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

OUTBOX_STATUS = postgresql.ENUM(
    "pending",
    "publishing",
    "published",
    "failed",
    "dead_letter",
    name="outbox_status",
    create_type=False,
)

OUTBOX_EVENT_TYPE = postgresql.ENUM(
    "memory.extract.requested",
    "memory.summary.requested",
    "memory.embed.requested",
    "memory.cleanup.requested",
    name="outbox_event_type",
    create_type=False,
)

MEMORY_STATUS = postgresql.ENUM(
    "candidate",
    "active",
    "superseded",
    "expired",
    "rejected",
    "deleted",
    name="memory_status",
    create_type=False,
)

MEMORY_EVENT_TYPE = postgresql.ENUM(
    "created",
    "updated",
    "confirmed",
    "superseded",
    "rejected",
    "expired",
    "deleted",
    name="memory_event_type",
    create_type=False,
)

MEMORY_ACTOR_TYPE = postgresql.ENUM(
    "user",
    "agent",
    "system",
    name="memory_actor_type",
    create_type=False,
)

ENUMS = (OUTBOX_STATUS, OUTBOX_EVENT_TYPE, MEMORY_STATUS, MEMORY_EVENT_TYPE, MEMORY_ACTOR_TYPE)


def source_columns() -> list[sa.Column]:

    """The message, conversation and run a memory row came from."""

    return [
        sa.Column("source_message_id", sa.BigInteger(), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("source_conversation_id", sa.BigInteger(), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("source_run_id", sa.BigInteger(), sa.ForeignKey("agent_runs.id"), nullable=True),
    ]


def upgrade() -> None:

    """Create the five enum types, then outbox_events, memory_items and memory_events with their indexes."""

    for enum in ENUMS:
        enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("event_type", OUTBOX_EVENT_TYPE, nullable=False),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", OUTBOX_STATUS, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "event_type",
            "aggregate_type",
            "aggregate_id",
            name="uq_outbox_events_event_aggregate",
        ),
    )

    op.create_index("idx_outbox_events_status_available", "outbox_events", ["status", "available_at"])

    op.create_table(
        "memory_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("memory_type", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("memory_key", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("confirmed_by_user", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", MEMORY_STATUS, nullable=False, server_default="active"),
        *source_columns(),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_memory_items_user_status", "memory_items", ["user_id", "status"])
    op.create_index(
        "uq_memory_items_one_active_key",
        "memory_items",
        ["user_id", "namespace", "memory_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "memory_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("memory_id", sa.BigInteger(), sa.ForeignKey("memory_items.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", MEMORY_EVENT_TYPE, nullable=False),
        sa.Column("old_content", postgresql.JSONB(), nullable=True),
        sa.Column("new_content", postgresql.JSONB(), nullable=True),
        *source_columns(),
        sa.Column("outbox_event_id", sa.BigInteger(), sa.ForeignKey("outbox_events.id"), nullable=True),
        sa.Column("actor_type", MEMORY_ACTOR_TYPE, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_memory_events_memory_id", "memory_events", ["memory_id"])
    op.create_index("ix_memory_events_outbox_event_id", "memory_events", ["outbox_event_id"])


def downgrade() -> None:

    """Drop the three tables in reverse order, then the five enum types."""

    op.drop_index("ix_memory_events_outbox_event_id", table_name="memory_events")
    op.drop_index("ix_memory_events_memory_id", table_name="memory_events")
    op.drop_table("memory_events")

    op.drop_index("uq_memory_items_one_active_key", table_name="memory_items")
    op.drop_index("ix_memory_items_user_status", table_name="memory_items")
    op.drop_table("memory_items")

    op.drop_index("idx_outbox_events_status_available", table_name="outbox_events")
    op.drop_table("outbox_events")

    for enum in reversed(ENUMS):
        enum.drop(op.get_bind(), checkfirst=False)
