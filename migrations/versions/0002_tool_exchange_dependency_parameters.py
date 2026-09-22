from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0002_tool_exchange_dependency_parameters"
down_revision = "0001_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tool_exchanges",
        sa.Column("dependency_parameters", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("tool_exchanges", "dependency_parameters")
