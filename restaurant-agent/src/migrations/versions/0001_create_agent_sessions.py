"""Create agent-owned session and idempotency tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_sessions_customer_id", "agent_sessions", ["customer_id"])
    op.create_table(
        "agent_message_idempotency",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "client_message_id"),
    )
    op.create_index("ix_agent_message_idempotency_session_id", "agent_message_idempotency", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_message_idempotency_session_id", table_name="agent_message_idempotency")
    op.drop_table("agent_message_idempotency")
    op.drop_index("ix_agent_sessions_customer_id", table_name="agent_sessions")
    op.drop_table("agent_sessions")
