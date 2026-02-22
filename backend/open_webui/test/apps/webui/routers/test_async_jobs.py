"""
Integration tests for the async jobs REST API router.

These tests build a minimal FastAPI app that mounts only the jobs router,
avoiding the need to import open_webui.main (which pulls in loguru and other
missing test dependencies).

All external dependencies (DB, redis, generate_chat_completion, create_task,
stop_item_tasks) are mocked.

Run:
    cd backend
    __test_venv/bin/pytest open_webui/test/apps/webui/routers/test_async_jobs.py -v
"""

import sys
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Pre-mock heavy internal modules so importing our router doesn't crash
_fake_db_module = MagicMock()
_fake_db_module.Base = MagicMock()
_fake_db_module.get_db_context = MagicMock()
sys.modules.setdefault("open_webui.internal.db", _fake_db_module)
sys.modules.setdefault("open_webui.internal", MagicMock())
sys.modules.setdefault("open_webui.tasks", MagicMock())

from fastapi import FastAPI, Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# We need get_verified_user — mock it in the router module namespace
_fake_user = MagicMock()
_fake_user.id = "default-user"
_fake_user.job_priority = 5


async def _fake_get_verified_user():
    return _fake_user


# Patch auth before importing router
sys.modules["open_webui.utils.auth"] = MagicMock()
sys.modules["open_webui.utils.auth"].get_verified_user = _fake_get_verified_user
sys.modules["open_webui.utils.chat"] = MagicMock()

from open_webui.models.jobs import (  # noqa: E402
    JobsTable,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_CANCELLED,
)
from open_webui.routers.jobs import router  # noqa: E402

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Minimal FastAPI app with just the jobs router."""
    _app = FastAPI()
    _app.include_router(router, prefix="/jobs")
    _app.state.redis = None
    _app.state.MODELS = {
        "llama3": {"id": "llama3", "name": "Llama 3", "owned_by": "ollama"}
    }
    return _app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/jobs"
PAYLOAD = {"model": "llama3", "messages": [{"role": "user", "content": "Hello!"}]}
RESULT = {"choices": [{"message": {"content": "Hi!"}}]}


def _patch_jobs_table(job=None, job_list=None, total=0):
    """Return a context manager that patches the Jobs singleton methods."""
    mock_jobs = MagicMock()
    mock_jobs.insert_new_job.return_value = job
    mock_jobs.get_job_by_id.return_value = job
    mock_jobs.get_jobs_by_user_id.return_value = job_list or []
    mock_jobs.count_jobs_by_user_id.return_value = total
    mock_jobs.update_job_running.return_value = job
    mock_jobs.update_job_completed.return_value = job
    mock_jobs.update_job_failed.return_value = job
    mock_jobs.update_job_cancelled.return_value = (
        job if job else MagicMock(status=JOB_STATUS_CANCELLED)
    )
    mock_jobs.delete_job_by_id.return_value = True
    return patch("open_webui.routers.jobs.Jobs", mock_jobs), mock_jobs


def _new_job(job_id=None, user_id="default-user", status=JOB_STATUS_QUEUED):
    job = MagicMock()
    job.id = job_id or str(uuid.uuid4())
    job.user_id = user_id
    job.status = status
    job.model_id = "llama3"
    job.backend_url = None
    job.attempt_count = 0
    job.max_attempts = 3
    job.priority = 5
    job.priority_score = 5.0
    job.result = None
    job.error = None
    job.created_at = 1700000000
    job.updated_at = 1700000000
    return job


# ---------------------------------------------------------------------------
# POST /jobs/chat/completions — Submit
# ---------------------------------------------------------------------------


def test_submit_returns_202_and_job_id(client):
    job = _new_job()
    patcher, mock_jobs = _patch_jobs_table(job=job)

    async def _fake_create_task(*args, **kwargs):
        pass  # do nothing

    with patcher, patch("open_webui.routers.jobs.create_task", _fake_create_task):
        resp = client.post(f"{BASE}/chat/completions", json=PAYLOAD)

    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == JOB_STATUS_QUEUED


def test_submit_unknown_model_returns_404(client):
    payload = {**PAYLOAD, "model": "no-such-model"}
    resp = client.post(f"{BASE}/chat/completions", json=payload)
    assert resp.status_code == 404


def test_submit_when_job_creation_fails_returns_500(client):
    patcher, mock_jobs = _patch_jobs_table(job=None)
    with patcher:
        resp = client.post(f"{BASE}/chat/completions", json=PAYLOAD)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} — Poll
# ---------------------------------------------------------------------------


def test_get_job_returns_queued_status(client):
    job = _new_job(status=JOB_STATUS_QUEUED)
    patcher, _ = _patch_jobs_table(job=job)
    with patcher:
        resp = client.get(f"{BASE}/{job.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == JOB_STATUS_QUEUED
    assert resp.json()["result"] is None


def test_get_job_completed_includes_result(client):
    job = _new_job(status=JOB_STATUS_COMPLETED)
    job.result = RESULT
    patcher, _ = _patch_jobs_table(job=job)
    with patcher:
        resp = client.get(f"{BASE}/{job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == JOB_STATUS_COMPLETED
    assert data["result"] == RESULT


def test_get_job_not_found_returns_404(client):
    patcher, mock_jobs = _patch_jobs_table(job=None)
    with patcher:
        resp = client.get(f"{BASE}/nonexistent-id")
    assert resp.status_code == 404


def test_get_job_other_users_job_returns_403(client):
    """The job belongs to a different user."""
    job = _new_job(user_id="someone-else")
    patcher, _ = _patch_jobs_table(job=job)
    with patcher:
        resp = client.get(f"{BASE}/{job.id}")
    assert resp.status_code == 403


def test_get_job_without_result_flag_omits_result(client):
    job = _new_job(status=JOB_STATUS_COMPLETED)
    job.result = RESULT
    patcher, _ = _patch_jobs_table(job=job)
    with patcher:
        resp = client.get(f"{BASE}/{job.id}?include_result=false")
    assert resp.status_code == 200
    assert resp.json()["result"] is None


# ---------------------------------------------------------------------------
# DELETE /jobs/{job_id} — Cancel
# ---------------------------------------------------------------------------


def test_cancel_queued_job_returns_200_and_cancelled(client):
    job = _new_job(status=JOB_STATUS_QUEUED)
    cancelled_job = _new_job(job_id=job.id, status=JOB_STATUS_CANCELLED)
    patcher, mock_jobs = _patch_jobs_table(job=job)
    mock_jobs.update_job_cancelled.return_value = cancelled_job

    async def _fake_stop(*args, **kwargs):
        pass

    with patcher, patch("open_webui.routers.jobs.stop_item_tasks", _fake_stop):
        resp = client.delete(f"{BASE}/{job.id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == JOB_STATUS_CANCELLED


def test_cancel_nonexistent_job_returns_404(client):
    patcher, mock_jobs = _patch_jobs_table(job=None)
    with patcher:
        resp = client.delete(f"{BASE}/nonexistent")
    assert resp.status_code == 404


def test_cancel_other_users_job_returns_403(client):
    job = _new_job(user_id="someone-else")
    patcher, _ = _patch_jobs_table(job=job)
    with patcher:
        resp = client.delete(f"{BASE}/{job.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /jobs — List
# ---------------------------------------------------------------------------


def test_list_jobs_returns_paginated_response(client):
    jobs = [_new_job() for _ in range(3)]
    patcher, _ = _patch_jobs_table(job_list=jobs, total=3)
    with patcher:
        resp = client.get(BASE)
    assert resp.status_code == 200
    data = resp.json()
    assert "jobs" in data
    assert data["total"] == 3
    assert len(data["jobs"]) == 3


def test_list_jobs_empty_for_new_user(client):
    patcher, _ = _patch_jobs_table(job_list=[], total=0)
    with patcher:
        resp = client.get(BASE)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_jobs_pagination_params_forwarded(client):
    patcher, mock_jobs = _patch_jobs_table(job_list=[], total=10)
    with patcher:
        resp = client.get(f"{BASE}?skip=5&limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["skip"] == 5
    assert data["limit"] == 2
    mock_jobs.get_jobs_by_user_id.assert_called_once_with(
        _fake_user.id, skip=5, limit=2, status=None, model_id=None
    )
