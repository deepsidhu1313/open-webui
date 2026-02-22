"""
models/backend_snapshots.py — ORM + DAL for the `backend_snapshot` table.

Each row captures a point-in-time snapshot of a single Ollama backend's
health: CPU/RAM, Ollama VRAM + loaded models, and job queue depth.

Snapshots are taken every SNAPSHOT_INTERVAL_SECONDS (default 5 min) by
a background scheduler loop defined in utils/job_scheduler.py.
"""

import time
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, Float, Index, Integer, Text

from open_webui.internal.db import Base, get_db_context


class BackendSnapshot(Base):
    __tablename__ = "backend_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(BigInteger, nullable=False)   # epoch seconds
    backend_url = Column(Text, nullable=False)

    # System-level (WebUI host) — single set per snapshot tick
    cpu_percent = Column(Float, nullable=True)
    ram_percent = Column(Float, nullable=True)

    # Job queue
    active_jobs = Column(Integer, nullable=True)
    queued_jobs = Column(Integer, nullable=True)

    # Ollama-specific (from /api/ps against this backend)
    loaded_models = Column(Integer, nullable=True)
    vram_used_gb = Column(Float, nullable=True)

    # Performance
    avg_tokens_per_second = Column(Float, nullable=True)

    __table_args__ = (
        Index("backend_snapshot_backend_url_idx", "backend_url"),
        Index("backend_snapshot_captured_at_idx", "captured_at"),
    )


class BackendSnapshotModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    captured_at: int
    backend_url: str
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    active_jobs: Optional[int] = None
    queued_jobs: Optional[int] = None
    loaded_models: Optional[int] = None
    vram_used_gb: Optional[float] = None
    avg_tokens_per_second: Optional[float] = None


class BackendSnapshotsTable:
    """Data Access Layer for the backend_snapshot table."""

    def insert(self, row: dict, db=None) -> Optional[BackendSnapshotModel]:
        with get_db_context(db) as db:
            snap = BackendSnapshot(**{k: v for k, v in row.items() if hasattr(BackendSnapshot, k)})
            db.add(snap)
            db.commit()
            db.refresh(snap)
            return BackendSnapshotModel.model_validate(snap)

    def get_recent(
        self,
        backend_url: str,
        limit: int = 60,
        since: Optional[int] = None,
        db=None,
    ) -> list[BackendSnapshotModel]:
        """Return the most recent `limit` snapshots for a specific backend, oldest-first."""
        with get_db_context(db) as db:
            q = (
                db.query(BackendSnapshot)
                .filter(BackendSnapshot.backend_url == backend_url)
            )
            if since:
                q = q.filter(BackendSnapshot.captured_at >= since)
            q = q.order_by(BackendSnapshot.captured_at.desc()).limit(limit)
            rows = list(reversed(q.all()))
            return [BackendSnapshotModel.model_validate(r) for r in rows]

    def get_all_backends(self, db=None) -> list[str]:
        """Return distinct backend URLs that have snapshots."""
        with get_db_context(db) as db:
            rows = db.query(BackendSnapshot.backend_url).distinct().all()
            return [r[0] for r in rows]

    def purge_old(self, older_than_days: int = 7, db=None) -> int:
        """Delete snapshots older than `older_than_days`. Returns number deleted."""
        cutoff = int(time.time()) - older_than_days * 86_400
        with get_db_context(db) as db:
            n = (
                db.query(BackendSnapshot)
                .filter(BackendSnapshot.captured_at < cutoff)
                .delete()
            )
            db.commit()
            return n


BackendSnapshots = BackendSnapshotsTable()
