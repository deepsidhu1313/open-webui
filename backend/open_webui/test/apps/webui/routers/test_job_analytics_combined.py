"""
test_job_analytics_combined.py  —  C2: Analytics integration tests.

Uses an in-memory SQLite engine to seed real data and exercise
get_combined_analytics() + get_job_analytics() end-to-end.

Run:
    cd backend
    .test_venv311/bin/pytest \
        open_webui/test/apps/webui/routers/test_job_analytics_combined.py -v
"""

import sys
import time
import uuid
from contextlib import contextmanager

# Pre-mock the internal DB module before importing anything from open_webui
from unittest.mock import MagicMock, patch

_fake_db = MagicMock()
_fake_db.Base = MagicMock()
sys.modules.setdefault("open_webui.internal.db", _fake_db)
sys.modules.setdefault("open_webui.internal", MagicMock())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import real ORM classes so we can create the schema
# (at this point the SQLAlchemy Base is real; the pre-mock above is only for
#  the *module import* path — we rebuild with a real engine here)
from sqlalchemy.orm import DeclarativeBase

import open_webui.models.jobs as jobs_mod

# Rebuild a fresh in-memory SQLite engine + session for tests
_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

# Recreate Base & tables using the *real* ORM classes already imported
from open_webui.models.jobs import (  # noqa: E402
    Job, JobArchive,
    JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED, JOB_STATUS_QUEUED,
    JobsTable, JobArchiveTable,
)

# Create schema in the in-memory SQLite DB
# (Base.metadata comes from the real SQLAlchemy Base the ORM classes extend)
try:
    from open_webui.internal.db import Base as _RealBase  # may fail if pre-mocked
    _RealBase.metadata.create_all(_engine)
except Exception:
    # Fallback: use the metadata attached to the real Job class
    Job.metadata.create_all(_engine)

_Session = sessionmaker(bind=_engine)

NOW = int(time.time())
DAY = 86_400


def _job(status, model="llama3", user_id="u1", days_ago=5):
    """Create and return a Job ORM row (not committed)."""
    ts = NOW - days_ago * DAY
    return Job(
        id=str(uuid.uuid4()),
        user_id=user_id,
        status=status,
        priority=5,
        priority_score=5.0,
        model_id=model,
        backend_url=None,
        request={},
        result={"choices": []} if status == JOB_STATUS_COMPLETED else None,
        error="oops" if status == JOB_STATUS_FAILED else None,
        attempt_count=1,
        max_attempts=3,
        created_at=ts,
        updated_at=ts + 10,
    )


def _archive(status, model="llama3", user_id="u2", days_ago=40):
    """Create and return a JobArchive ORM row (not committed)."""
    ts = NOW - days_ago * DAY
    return JobArchive(
        id=str(uuid.uuid4()),
        user_id=user_id,
        status=status,
        priority=5,
        priority_score=5.0,
        model_id=model,
        backend_url=None,
        request={},
        result=None,
        error=None,
        attempt_count=1,
        max_attempts=3,
        created_at=ts,
        updated_at=ts + 10,
        archived_at=NOW - 35 * DAY,
    )


@contextmanager
def _db():
    """Provide a fresh session and auto-rollback after each test."""
    session = _Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# Test helpers that patch get_db_context to use our real SQLite session
# ---------------------------------------------------------------------------

@contextmanager
def _real_db_ctx_for(session):
    """Drop-in replacement for get_db_context that yields our SQLite session."""
    @contextmanager
    def _stub(_db=None):
        yield session
    with patch("open_webui.models.jobs.get_db_context", _stub):
        yield


# ============================================================================
# Tests
# ============================================================================


class TestGetJobAnalytics:
    """Test JobsTable.get_job_analytics() against real SQLite data."""

    def test_empty_db_returns_zero_total(self):
        with _db() as session, _real_db_ctx_for(session):
            result = JobsTable().get_job_analytics(db=session)
        assert result["total"] == 0
        assert result["success_rate"] == 0.0
        assert result["by_model"] == []

    def test_counts_by_status(self):
        with _db() as session:
            session.add(_job(JOB_STATUS_COMPLETED))
            session.add(_job(JOB_STATUS_FAILED))
            session.add(_job(JOB_STATUS_QUEUED))
            session.commit()

            with _real_db_ctx_for(session):
                result = JobsTable().get_job_analytics(db=session)

        assert result["total"] == 3
        assert result["by_status"][JOB_STATUS_COMPLETED] == 1
        assert result["by_status"][JOB_STATUS_FAILED] == 1
        assert result["success_rate"] == round(1 / 3 * 100, 1)

    def test_by_model_top20(self):
        with _db() as session:
            for _ in range(3):
                session.add(_job(JOB_STATUS_COMPLETED, model="gpt4"))
            session.add(_job(JOB_STATUS_FAILED, model="llama3"))
            session.commit()

            with _real_db_ctx_for(session):
                result = JobsTable().get_job_analytics(db=session)

        models = {r["model_id"]: r for r in result["by_model"]}
        assert "gpt4" in models
        assert models["gpt4"]["completed"] == 3
        assert models["llama3"]["failed"] == 1


class TestGetCombinedAnalytics:
    """Test JobArchiveTable.get_combined_analytics() against real SQLite data."""

    def test_empty_returns_zero_total(self):
        with _db() as session, _real_db_ctx_for(session):
            result = JobArchiveTable().get_combined_analytics(db=session)
        assert result["total"] == 0
        assert result["includes_archive"] is True
        assert "daily_history" in result
        assert "by_user" in result

    def test_union_includes_archive_rows(self):
        """Archived rows must appear in combined totals."""
        with _db() as session:
            session.add(_job(JOB_STATUS_COMPLETED))       # active
            session.add(_archive(JOB_STATUS_COMPLETED))   # archived
            session.commit()

            with _real_db_ctx_for(session), \
                 patch("open_webui.models.jobs.Users", None):
                result = JobArchiveTable().get_combined_analytics(db=session)

        assert result["total"] == 2
        assert result["by_status"].get(JOB_STATUS_COMPLETED, 0) == 2

    def test_daily_history_contains_today(self):
        """Jobs created today should appear in daily_history."""
        with _db() as session:
            session.add(_job(JOB_STATUS_COMPLETED, days_ago=0))
            session.add(_job(JOB_STATUS_FAILED, days_ago=0))
            session.commit()

            with _real_db_ctx_for(session), \
                 patch("open_webui.models.jobs.Users", None):
                result = JobArchiveTable().get_combined_analytics(db=session)

        import datetime
        today = datetime.date.today().isoformat()
        dates = {row["date"] for row in result["daily_history"]}
        assert today in dates

    def test_daily_history_old_rows_excluded(self):
        """Jobs created 95 days ago (> 90 day window) must NOT appear."""
        with _db() as session:
            session.add(_job(JOB_STATUS_COMPLETED, days_ago=95))
            session.commit()

            with _real_db_ctx_for(session), \
                 patch("open_webui.models.jobs.Users", None):
                result = JobArchiveTable().get_combined_analytics(db=session)

        assert result["daily_history"] == []

    def test_by_user_aggregation(self):
        """by_user must group by user_id and sum correctly."""
        with _db() as session:
            for _ in range(2):
                session.add(_job(JOB_STATUS_COMPLETED, user_id="alice"))
            session.add(_job(JOB_STATUS_FAILED, user_id="alice"))
            session.add(_job(JOB_STATUS_COMPLETED, user_id="bob"))
            session.commit()

            with _real_db_ctx_for(session), \
                 patch("open_webui.models.jobs.Users", None):
                result = JobArchiveTable().get_combined_analytics(db=session)

        by_uid = {r["user_id"]: r for r in result["by_user"]}
        assert by_uid["alice"]["total"] == 3
        assert by_uid["alice"]["completed"] == 2
        assert by_uid["alice"]["failed"] == 1
        assert by_uid["bob"]["total"] == 1

    def test_by_model_appears_in_combined(self):
        with _db() as session:
            session.add(_job(JOB_STATUS_COMPLETED, model="phi3"))
            session.add(_archive(JOB_STATUS_COMPLETED, model="phi3"))
            session.commit()

            with _real_db_ctx_for(session), \
                 patch("open_webui.models.jobs.Users", None):
                result = JobArchiveTable().get_combined_analytics(db=session)

        model_ids = [r["model_id"] for r in result["by_model"]]
        assert "phi3" in model_ids

    def test_success_rate_calculation(self):
        with _db() as session:
            for _ in range(3):
                session.add(_job(JOB_STATUS_COMPLETED))
            session.add(_job(JOB_STATUS_FAILED))
            session.commit()

            with _real_db_ctx_for(session), \
                 patch("open_webui.models.jobs.Users", None):
                result = JobArchiveTable().get_combined_analytics(db=session)

        assert result["success_rate"] == 75.0
