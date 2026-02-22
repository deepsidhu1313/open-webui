"""add job_archive table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-21

Adds a `job_archive` table with identical schema to `job`, used for long-term
retention of completed / failed / cancelled jobs after the active-table
retention window (JOB_RETENTION_DAYS) expires.
"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_archive",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("priority_score", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("backend_url", sa.Text(), nullable=True),
        sa.Column("request", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        # When the row was moved to the archive
        sa.Column("archived_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("job_archive_user_id_idx", "job_archive", ["user_id"])
    op.create_index("job_archive_status_idx", "job_archive", ["status"])
    op.create_index("job_archive_created_at_idx", "job_archive", ["created_at"])
    op.create_index("job_archive_archived_at_idx", "job_archive", ["archived_at"])


def downgrade():
    op.drop_table("job_archive")
