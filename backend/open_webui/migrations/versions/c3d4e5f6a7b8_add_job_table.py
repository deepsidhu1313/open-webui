"""Add job table for async job queue API

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-20 20:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="queued",
        ),
        # Priority fields (Phase 2 — scheduler)
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("priority_score", sa.Float(), nullable=False, server_default="5.0"),
        # What was requested / where it went
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("backend_url", sa.Text(), nullable=True),
        # Payload / result / error
        sa.Column("request", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        # Retry counters
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        # Timestamps
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )

    op.create_index("job_user_id_idx", "job", ["user_id"])
    op.create_index("job_user_status_idx", "job", ["user_id", "status"])
    op.create_index("job_created_at_idx", "job", ["created_at"])
    op.create_index(
        "job_status_priority_score_idx", "job", ["status", "priority_score"]
    )


def downgrade() -> None:
    op.drop_index("job_status_priority_score_idx", table_name="job")
    op.drop_index("job_created_at_idx", table_name="job")
    op.drop_index("job_user_status_idx", table_name="job")
    op.drop_index("job_user_id_idx", table_name="job")
    op.drop_table("job")
