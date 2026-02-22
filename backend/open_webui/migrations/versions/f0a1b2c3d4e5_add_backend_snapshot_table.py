"""f0a1b2c3d4e5_add_backend_snapshot_table

Revision ID: f0a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-02-21

Adds `backend_snapshot` table for time-series metrics of each Ollama backend.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "f0a1b2c3d4e5"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "backend_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("captured_at", sa.BigInteger, nullable=False),   # epoch seconds
        sa.Column("backend_url", sa.Text, nullable=False),
        # System-level metrics (from psutil on WebUI server)
        sa.Column("cpu_percent", sa.Float, nullable=True),
        sa.Column("ram_percent", sa.Float, nullable=True),
        # Job queue metrics
        sa.Column("active_jobs", sa.Integer, nullable=True),   # running
        sa.Column("queued_jobs", sa.Integer, nullable=True),   # waiting
        # Ollama-specific (from /api/ps)
        sa.Column("loaded_models", sa.Integer, nullable=True),
        sa.Column("vram_used_gb", sa.Float, nullable=True),
        # Optional: tokens/s from EMA tracker
        sa.Column("avg_tokens_per_second", sa.Float, nullable=True),
    )
    op.create_index("backend_snapshot_backend_url_idx", "backend_snapshot", ["backend_url"])
    op.create_index("backend_snapshot_captured_at_idx", "backend_snapshot", ["captured_at"])


def downgrade():
    op.drop_index("backend_snapshot_captured_at_idx", table_name="backend_snapshot")
    op.drop_index("backend_snapshot_backend_url_idx", table_name="backend_snapshot")
    op.drop_table("backend_snapshot")
