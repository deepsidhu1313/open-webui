"""
Unit tests for the job scheduler (Phase 2).

Tests the priority/starvation logic and the system metrics router
using pre-mocked DB and psutil.

Run:
    cd backend
    .test_venv311/bin/pytest open_webui/test/apps/webui/routers/test_scheduler.py -v
"""

import sys
import time
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# Pre-mock DB and heavy internals
_fake_db_module = MagicMock()
_fake_db_module.Base = MagicMock()
_fake_db_module.get_db_context = MagicMock()
sys.modules.setdefault("open_webui.internal.db", _fake_db_module)
sys.modules.setdefault("open_webui.internal", MagicMock())
sys.modules.setdefault("open_webui.tasks", MagicMock())
sys.modules.setdefault("open_webui.utils.auth", MagicMock())
sys.modules.setdefault("open_webui.utils.chat", MagicMock())

# ---------------------------------------------------------------------------
# scheduler logic tests
# ---------------------------------------------------------------------------

from open_webui.models.jobs import (  # noqa: E402
    JobsTable,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
)

Jobs = JobsTable()


def _make_mock_job(
    job_id=None,
    status=JOB_STATUS_QUEUED,
    attempt_count=0,
    max_attempts=3,
    priority_score=5.0,
):
    job = MagicMock()
    job.id = job_id or str(uuid.uuid4())
    job.user_id = "user-1"
    job.model_id = "llama3"
    job.status = status
    job.priority_score = priority_score
    job.attempt_count = attempt_count
    job.max_attempts = max_attempts
    job.request = {"model": "llama3", "messages": []}
    job.result = None
    job.error = None
    job.created_at = int(time.time())
    job.updated_at = int(time.time())
    return job


@contextmanager
def _mock_db(job=None):
    """Yield a mock DB session that returns `job` on first()."""
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.first.return_value = job
    # Also support order_by / with_for_update chaining
    chain.order_by.return_value = chain
    chain.with_for_update.return_value = chain

    @contextmanager
    def _fake(_db=None):
        yield db

    mock_job_class = MagicMock()
    mock_job_class.id = MagicMock()
    mock_job_class.status = MagicMock()
    mock_job_class.priority_score = MagicMock()

    with patch("open_webui.models.jobs.get_db_context", _fake), \
         patch("open_webui.models.jobs.Job", mock_job_class):
        yield db


# ---------------------------------------------------------------------------
# Test: retry logic via update_job_failed
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def test_failed_job_requeued_when_attempts_remain(self):
        mock_job = _make_mock_job(attempt_count=1, max_attempts=3)
        with _mock_db(job=mock_job):
            with patch("open_webui.models.jobs.JobModel") as mock_model:
                mock_model.model_validate.return_value = mock_model
                Jobs.update_job_failed(mock_job.id, error="err", requeue=True)
        assert mock_job.status == JOB_STATUS_QUEUED

    def test_failed_job_stays_failed_at_max_attempts(self):
        mock_job = _make_mock_job(attempt_count=3, max_attempts=3)
        with _mock_db(job=mock_job):
            with patch("open_webui.models.jobs.JobModel") as mock_model:
                mock_model.model_validate.return_value = mock_model
                Jobs.update_job_failed(mock_job.id, error="err", requeue=True)
        assert mock_job.status == JOB_STATUS_FAILED

    def test_exponential_backoff_attempt_count_increment(self):
        """Each run() call increments attempt_count by 1."""
        mock_job = _make_mock_job(attempt_count=0)
        with _mock_db(job=mock_job):
            with patch("open_webui.models.jobs.JobModel") as mock_model:
                mock_model.model_validate.return_value = mock_model
                Jobs.update_job_running(mock_job.id)
        assert mock_job.attempt_count == 1


# ---------------------------------------------------------------------------
# Test: scheduler helper — _bump_stale_jobs
# ---------------------------------------------------------------------------

class TestStarvationPrevention:
    def test_bump_stale_jobs_updates_all_queued_jobs(self):
        """_bump_stale_jobs should run an UPDATE on the job table for queued rows."""
        from open_webui.utils import job_scheduler

        with patch("open_webui.utils.job_scheduler.get_db_context") as mock_ctx, \
             patch("open_webui.utils.job_scheduler.Job") as MockJob:

            db = MagicMock()

            @contextmanager
            def _fake(_db=None):
                yield db

            mock_ctx.side_effect = _fake
            MockJob.status = MagicMock()
            MockJob.priority_score = MagicMock()

            with patch("open_webui.utils.job_scheduler.update") as mock_update:
                mock_update.return_value.where.return_value.values.return_value = MagicMock()
                job_scheduler._bump_stale_jobs()

            db.execute.assert_called_once()
            db.commit.assert_called_once()

    def test_bump_stale_jobs_handles_db_error_gracefully(self):
        """Starvation loop should not raise even if DB fails."""
        from open_webui.utils import job_scheduler

        @contextmanager
        def _raise(_db=None):
            raise RuntimeError("Connection refused")
            yield

        with patch("open_webui.utils.job_scheduler.get_db_context", _raise):
            # Should not raise
            job_scheduler._bump_stale_jobs()


# ---------------------------------------------------------------------------
# Test: system metrics router
# ---------------------------------------------------------------------------

class TestSystemMetrics:
    def test_local_metrics_returns_expected_keys(self):
        """_local_metrics should return cpu, ram, disk info."""
        import psutil

        with patch.object(psutil, "cpu_percent", return_value=23.5), \
             patch.object(psutil, "virtual_memory", return_value=MagicMock(
                 total=8 * 1_073_741_824,
                 used=4 * 1_073_741_824,
                 percent=50.0,
             )), \
             patch.object(psutil, "disk_usage", return_value=MagicMock(
                 total=500 * 1_073_741_824,
                 used=200 * 1_073_741_824,
                 percent=40.0,
             )):
            from open_webui.routers.system import _local_metrics
            metrics = _local_metrics()

        assert metrics["cpu_percent"] == 23.5
        assert metrics["ram_percent"] == 50.0
        assert metrics["disk_percent"] == 40.0
        assert "ram_total_gb" in metrics
        assert "disk_used_gb" in metrics

    @pytest.mark.anyio
    async def test_system_metrics_endpoint_returns_200(self):
        """GET /api/v1/system/metrics (admin) returns server + ollama_backends."""
        import psutil
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from open_webui.routers.system import router, get_admin_user

        fake_admin = MagicMock(id="admin-1", role="admin")

        async def _override():
            return fake_admin

        _app = FastAPI()
        _app.include_router(router, prefix="/system")
        _app.dependency_overrides[get_admin_user] = _override

        fake_config = MagicMock()
        fake_config.ENABLE_OLLAMA_API = False
        fake_config.OLLAMA_BASE_URLS = []
        _app.state.config = fake_config

        with patch("open_webui.routers.system._local_metrics", return_value={
            "cpu_percent": 10.0,
            "ram_percent": 30.0,
            "disk_percent": 20.0,
        }):
            client = TestClient(_app)
            resp = client.get("/system/metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert "server" in data
        assert data["server"]["cpu_percent"] == 10.0
        assert "ollama_backends" in data
