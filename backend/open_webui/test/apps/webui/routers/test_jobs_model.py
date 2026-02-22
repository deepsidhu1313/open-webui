"""
Unit tests for the jobs model layer — status transition logic.

Tests mock the internal DB module to avoid sqlalchemy/peewee dependency issues.
The Job ORM class is also patched so column attribute access (Job.id, etc.)
works without a real SQLAlchemy engine.

Run:
    cd backend
    __test_venv/bin/pytest open_webui/test/apps/webui/routers/test_jobs_model.py -v
"""

import sys
import time
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Pre-mock the internal DB module BEFORE importing our model, so we never
# hit the peewee / wrappers.py wildcard-import problem.
# ---------------------------------------------------------------------------

_fake_db_module = MagicMock()
_fake_db_module.Base = MagicMock()
_fake_db_module.get_db_context = MagicMock()
sys.modules.setdefault("open_webui.internal.db", _fake_db_module)
sys.modules.setdefault("open_webui.internal", MagicMock())

from open_webui.models.jobs import (  # noqa: E402
    JobsTable,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_CANCELLED,
    TERMINAL_STATUSES,
)

Jobs = JobsTable()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_ID = "test-user-001"
MODEL_ID = "llama3"
SAMPLE_REQUEST = {"model": MODEL_ID, "messages": [{"role": "user", "content": "Hi!"}]}


def _make_mock_job(
    job_id=None,
    user_id=USER_ID,
    model_id=MODEL_ID,
    status=JOB_STATUS_QUEUED,
    attempt_count=0,
    max_attempts=3,
    backend_url=None,
    result=None,
    error=None,
):
    """Return a Mock that looks like a Job ORM row."""
    job = MagicMock()
    job.id = job_id or str(uuid.uuid4())
    job.user_id = user_id
    job.model_id = model_id
    job.status = status
    job.priority = 5
    job.priority_score = 5.0
    job.backend_url = backend_url
    job.request = SAMPLE_REQUEST
    job.result = result
    job.error = error
    job.attempt_count = attempt_count
    job.max_attempts = max_attempts
    job.created_at = int(time.time())
    job.updated_at = int(time.time())
    return job


@contextmanager
def _mock_db(job=None):
    """
    Patch get_db_context to yield a mock session and also patch the Job ORM
    class so that column attributes (Job.id, Job.status, …) are accessible.
    """
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = job

    @contextmanager
    def _fake(_db=None):
        yield db

    # Patch both get_db_context and the Job ORM class
    mock_job_class = MagicMock()
    mock_job_class.id = MagicMock()
    mock_job_class.status = MagicMock()
    mock_job_class.user_id = MagicMock()

    with patch("open_webui.models.jobs.get_db_context", _fake), \
         patch("open_webui.models.jobs.Job", mock_job_class):
        yield db


# ---------------------------------------------------------------------------
# insert_new_job
# ---------------------------------------------------------------------------


def test_insert_adds_and_commits():
    mock_job = _make_mock_job()
    with _mock_db(job=mock_job) as db:
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = mock_model
            # Job constructor is already mocked by _mock_db via Job patch
            Jobs.insert_new_job(USER_ID, MODEL_ID, SAMPLE_REQUEST)

        db.add.assert_called_once()
        db.commit.assert_called_once()


def test_insert_sets_queued_status():
    mock_job = _make_mock_job()
    with _mock_db(job=mock_job) as db:
        mock_job_class = MagicMock()

        # Use a dedicated Job patch to inspect constructor kwargs
        with patch("open_webui.models.jobs.get_db_context") as mock_ctx, \
             patch("open_webui.models.jobs.Job", mock_job_class) as MockJob, \
             patch("open_webui.models.jobs.JobModel") as mock_model:
            db2 = MagicMock()

            @contextmanager
            def _fake(_db=None):
                yield db2

            mock_ctx.side_effect = _fake
            mock_job_class.return_value = mock_job
            mock_model.model_validate.return_value = mock_model

            Jobs.insert_new_job(USER_ID, MODEL_ID, SAMPLE_REQUEST)

        call_kwargs = mock_job_class.call_args.kwargs
        assert call_kwargs.get("status") == JOB_STATUS_QUEUED


def test_insert_uses_custom_priority():
    mock_job = _make_mock_job()
    with patch("open_webui.models.jobs.get_db_context") as mock_ctx, \
         patch("open_webui.models.jobs.Job") as MockJob, \
         patch("open_webui.models.jobs.JobModel") as mock_model:
        db = MagicMock()

        @contextmanager
        def _fake(_db=None):
            yield db

        mock_ctx.side_effect = _fake
        MockJob.return_value = mock_job
        mock_model.model_validate.return_value = mock_model

        Jobs.insert_new_job(USER_ID, MODEL_ID, SAMPLE_REQUEST, priority=8)

        call_kwargs = MockJob.call_args.kwargs
        assert call_kwargs.get("priority") == 8
        assert call_kwargs.get("priority_score") == 8.0


# ---------------------------------------------------------------------------
# get_job_by_id
# ---------------------------------------------------------------------------


def test_get_returns_none_for_missing():
    with _mock_db(job=None):
        result = Jobs.get_job_by_id("not-a-real-id")
    assert result is None


def test_get_returns_model_when_found():
    mock_job = _make_mock_job()
    with _mock_db(job=mock_job):
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = "validated"
            result = Jobs.get_job_by_id(mock_job.id)
    assert result == "validated"


# ---------------------------------------------------------------------------
# update_job_running
# ---------------------------------------------------------------------------


def test_running_sets_status_and_increments_attempts():
    mock_job = _make_mock_job(status=JOB_STATUS_QUEUED, attempt_count=0)
    with _mock_db(job=mock_job):
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = mock_model
            Jobs.update_job_running("job-id", backend_url="http://localhost:11434")

    assert mock_job.status == JOB_STATUS_RUNNING
    assert mock_job.attempt_count == 1
    assert mock_job.backend_url == "http://localhost:11434"


def test_running_returns_none_for_missing():
    with _mock_db(job=None):
        result = Jobs.update_job_running("not-a-real-id")
    assert result is None


# ---------------------------------------------------------------------------
# update_job_completed
# ---------------------------------------------------------------------------


def test_completed_stores_result():
    mock_job = _make_mock_job(status=JOB_STATUS_RUNNING)
    payload = {"choices": [{"message": {"content": "Hi!"}}]}
    with _mock_db(job=mock_job):
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = mock_model
            Jobs.update_job_completed("job-id", result=payload)

    assert mock_job.status == JOB_STATUS_COMPLETED
    assert mock_job.result == payload
    assert mock_job.error is None


# ---------------------------------------------------------------------------
# update_job_failed
# ---------------------------------------------------------------------------


def test_failed_when_max_attempts_reached():
    """attempt_count (1) == max_attempts (1) → FAILED, not re-queued."""
    mock_job = _make_mock_job(status=JOB_STATUS_RUNNING, attempt_count=1, max_attempts=1)
    with _mock_db(job=mock_job):
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = mock_model
            Jobs.update_job_failed("job-id", error="timeout", requeue=True)

    assert mock_job.status == JOB_STATUS_FAILED


def test_requeued_when_attempts_remain():
    """attempt_count (1) < max_attempts (3) AND requeue=True → QUEUED."""
    mock_job = _make_mock_job(status=JOB_STATUS_RUNNING, attempt_count=1, max_attempts=3)
    with _mock_db(job=mock_job):
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = mock_model
            Jobs.update_job_failed("job-id", error="timeout", requeue=True)

    assert mock_job.status == JOB_STATUS_QUEUED


def test_failed_without_requeue_flag():
    mock_job = _make_mock_job(status=JOB_STATUS_RUNNING, attempt_count=0, max_attempts=3)
    with _mock_db(job=mock_job):
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = mock_model
            Jobs.update_job_failed("job-id", error="fatal", requeue=False)

    assert mock_job.status == JOB_STATUS_FAILED


# ---------------------------------------------------------------------------
# update_job_cancelled
# ---------------------------------------------------------------------------


def test_cancelled_from_queued():
    mock_job = _make_mock_job(status=JOB_STATUS_QUEUED)
    with _mock_db(job=mock_job):
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = mock_model
            Jobs.update_job_cancelled("job-id")

    assert mock_job.status == JOB_STATUS_CANCELLED


def test_cancel_does_not_change_already_completed_job():
    """Cancelling an already-completed job leaves it completed."""
    mock_job = _make_mock_job(status=JOB_STATUS_COMPLETED)
    with _mock_db(job=mock_job):
        with patch("open_webui.models.jobs.JobModel") as mock_model:
            mock_model.model_validate.return_value = mock_model
            Jobs.update_job_cancelled("job-id")

    # TERMINAL_STATUSES check in model prevents overwrite
    assert mock_job.status == JOB_STATUS_COMPLETED


# ---------------------------------------------------------------------------
# delete_job_by_id
# ---------------------------------------------------------------------------


def test_delete_returns_true_on_success():
    with patch("open_webui.models.jobs.get_db_context") as mock_ctx, \
         patch("open_webui.models.jobs.Job") as MockJob:
        db = MagicMock()

        @contextmanager
        def _fake(_db=None):
            yield db

        mock_ctx.side_effect = _fake
        result = Jobs.delete_job_by_id("some-id")

    assert result is True
    db.commit.assert_called_once()


def test_delete_returns_false_on_exception():
    @contextmanager
    def _raising(_db=None):
        raise RuntimeError("DB error")
        yield  # unreachable

    with patch("open_webui.models.jobs.get_db_context", _raising):
        result = Jobs.delete_job_by_id("some-id")

    assert result is False


# ---------------------------------------------------------------------------
# Status constants / TERMINAL_STATUSES
# ---------------------------------------------------------------------------


def test_terminal_statuses_contains_expected_values():
    assert JOB_STATUS_COMPLETED in TERMINAL_STATUSES
    assert JOB_STATUS_FAILED in TERMINAL_STATUSES
    assert JOB_STATUS_CANCELLED in TERMINAL_STATUSES
    assert JOB_STATUS_QUEUED not in TERMINAL_STATUSES
    assert JOB_STATUS_RUNNING not in TERMINAL_STATUSES
