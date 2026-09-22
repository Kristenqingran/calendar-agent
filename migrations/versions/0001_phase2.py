from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0001_phase2"
down_revision = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(128), primary_key=True),
        sa.Column("assistant_timezone", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tasks",
        sa.Column("task_id", sa.String(128), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(128),
            sa.ForeignKey("conversations.conversation_id"),
            nullable=False,
        ),
        sa.Column("original_message", sa.Text(), nullable=False),
        sa.Column("object", sa.String(32), nullable=False),
        sa.Column("intent", sa.String(16), nullable=False),
        sa.Column("current_state", sa.String(40), nullable=False),
        sa.Column("final_status", sa.String(16)),
        sa.Column("current_step_id", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "task_parameters",
        sa.Column("task_id", sa.String(128), sa.ForeignKey("tasks.task_id"), primary_key=True),
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(30)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "task_steps",
        sa.Column("step_id", sa.String(128), primary_key=True),
        sa.Column("task_id", sa.String(128), sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("step_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_summary", sa.JSON()),
        sa.Column("output_summary", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "tool_exchanges",
        sa.Column("step_id", sa.String(128), sa.ForeignKey("task_steps.step_id"), primary_key=True),
        sa.Column("task_id", sa.String(128), sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("tool", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(40)),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON()),
        sa.Column("result_hash", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("queried_range", sa.JSON()),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("is_stale", sa.Boolean(), nullable=False),
        sa.Column("stale_reason", sa.Text()),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "operations",
        sa.Column("operation_id", sa.String(128), primary_key=True),
        sa.Column("task_id", sa.String(128), sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("tool", sa.String(50), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result_payload", sa.JSON()),
        sa.Column("verification_status", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "clarifications",
        sa.Column("step_id", sa.String(128), sa.ForeignKey("task_steps.step_id"), primary_key=True),
        sa.Column("task_id", sa.String(128), sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.JSON(), nullable=False),
        sa.Column("missing_fields", sa.JSON()),
        sa.Column("ambiguous_fields", sa.JSON()),
        sa.Column("blocked_from_state", sa.String(40), nullable=False),
        sa.Column("user_response", sa.JSON()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "state_transitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(128), sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("from_state", sa.String(40), nullable=False),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "inbound_receipts",
        sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(128),
            sa.ForeignKey("conversations.conversation_id"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(128), sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("message_type", sa.String(40), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("response_payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "inbound_receipts",
        "state_transitions",
        "clarifications",
        "operations",
        "tool_exchanges",
        "task_steps",
        "task_parameters",
        "tasks",
        "conversations",
    ):
        op.drop_table(table)
