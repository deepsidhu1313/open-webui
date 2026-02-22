"""
routers/jobs.py — Async job queue API router.

Endpoints (all under /api/v1/jobs):

    POST   /chat/completions   Submit a chat-completion job → 202 + job_id
    GET    /{job_id}           Poll status / retrieve result
    DELETE /{job_id}           Cancel a queued or running job
    GET    /                   List current user's jobs (paginated)

Design principles:
- HTTP layer only — no business logic. Business logic lives in models/jobs.py.
- Ownership enforced for every read / write: users only see their own jobs.
- generate_chat_completion runs in an asyncio background task so the HTTP
  response is returned immediately with 202.
- Redis is used to cache job status reads (TTL 10s) when available,
  invalidated on any status change.
"""

import asyncio
import csv
import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from open_webui.models.jobs import (
    Jobs,
    JobArchives,
    JobSubmitForm,
    JobResponse,
    JOB_STATUS_QUEUED,
    JOB_STATUS_FAILED,
    JOB_STATUS_CANCELLED,
    TERMINAL_STATUSES,
)
from open_webui.tasks import create_task, stop_item_tasks
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.chat import generate_chat_completion

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /analytics — Admin job analytics
# ---------------------------------------------------------------------------


@router.get(
    "/analytics",
    summary="Aggregate job statistics — active + archived (admin only)",
)
async def get_job_analytics(
    combined: bool = Query(True, description="Include archived rows in stats"),
    user=Depends(get_admin_user),
):
    """
    Returns aggregate job queue statistics.
    When `combined=true` (default) the numbers union `job` and `job_archive`
    for all-time history.  Pass `combined=false` for active-table only.
    """
    if combined:
        return JobArchives.get_combined_analytics()
    return Jobs.get_job_analytics()


# ---------------------------------------------------------------------------
# GET /analytics/export  — B4: stream daily_history as CSV
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/export",
    summary="Export analytics as CSV (admin only)",
)
async def export_analytics_csv(
    user=Depends(get_admin_user),
):
    """
    Returns a downloadable CSV with `daily_history` rows (date, total,
    completed, failed) from the combined job + archive analytics.
    """
    data = JobArchives.get_combined_analytics()
    daily = data.get("daily_history", [])
    by_model = data.get("by_model", [])

    buf = io.StringIO()
    writer = csv.writer(buf)

    # --- Daily history sheet ---
    writer.writerow(["section", "date", "total", "completed", "failed"])
    for row in daily:
        writer.writerow(["daily", row["date"], row["total"], row["completed"], row["failed"]])

    # --- By-model sheet ---
    writer.writerow([])
    writer.writerow(["section", "model_id", "total", "completed", "failed"])
    for row in by_model:
        writer.writerow(["model", row["model_id"], row["total"], row["completed"], row["failed"]])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=job_analytics.csv"},
    )


# ---------------------------------------------------------------------------
# GET /events  — B1: SSE stream of job status changes
# ---------------------------------------------------------------------------

# In-process registry: user_id -> set of asyncio.Queues
_SSE_QUEUES: dict[str, set] = {}


def _sse_publish(user_id: str, event: dict) -> None:
    """Called from update_job_* helpers to push events to waiting SSE clients."""
    for q in _SSE_QUEUES.get(user_id, set()):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


@router.get(
    "/events",
    summary="SSE stream of real-time job status updates (verified user)",
)
async def job_events(
    request: Request,
    user=Depends(get_verified_user),
):
    """
    Server-Sent Events endpoint.  Connect once from the browser and receive
    `{job_id, status, updated_at}` push events whenever one of your jobs
    changes state.

    Falls back gracefully: if the browser disconnects the generator exits.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    uid = user.id
    _SSE_QUEUES.setdefault(uid, set()).add(q)

    async def _generator():
        yield "data: {\"ping\": true}\n\n"  # heartbeat so proxies don't close the connection
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # SSE comment keeps connection alive
                if await request.is_disconnected():
                    break
        finally:
            _SSE_QUEUES.get(uid, set()).discard(q)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ---------------------------------------------------------------------------
# GET /archive   — Browse archived jobs (admin)
# GET /archive/config  — Return current retention settings
# POST /archive/run    — Manually trigger an archive sweep (admin)
# ---------------------------------------------------------------------------


@router.get(
    "/archive",
    summary="Browse archived jobs (admin only)",
)
async def list_archived_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    user=Depends(get_admin_user),
):
    """
    Paginated list of jobs that have been moved to `job_archive`.
    Newest-archived first.
    """
    rows = JobArchives.get_archived_jobs(
        status=status,
        model_id=model_id,
        skip=skip,
        limit=limit,
    )
    total = JobArchives.count_archived_jobs(status=status)
    return {
        "jobs": [r.model_dump() for r in rows],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get(
    "/archive/config",
    summary="Current retention configuration (admin only)",
)
async def get_archive_config(
    user=Depends(get_admin_user),
):
    """Returns the active JOB_RETENTION_DAYS and JOB_ARCHIVE_RETENTION_DAYS values."""
    from open_webui.utils.job_scheduler import (
        JOB_RETENTION_DAYS,
        JOB_ARCHIVE_RETENTION_DAYS,
    )
    return {
        "job_retention_days": JOB_RETENTION_DAYS,
        "job_archive_retention_days": JOB_ARCHIVE_RETENTION_DAYS,
        "note": (
            "Set JOB_RETENTION_DAYS / JOB_ARCHIVE_RETENTION_DAYS env vars to "
            "override. Archive purge is disabled when job_archive_retention_days=0."
        ),
    }


@router.post(
    "/archive/run",
    summary="Manually trigger an archive sweep (admin only)",
)
async def run_archive_sweep(
    user=Depends(get_admin_user),
):
    """
    Immediately run the archive + purge cycle without waiting for the
    next scheduled hourly sweep.  Useful for testing or urgent cleanup.
    """
    from open_webui.utils.job_scheduler import (
        JOB_RETENTION_DAYS,
        JOB_ARCHIVE_RETENTION_DAYS,
    )
    archived = JobArchives.archive_old_jobs(older_than_days=JOB_RETENTION_DAYS)
    purged = 0
    if JOB_ARCHIVE_RETENTION_DAYS > 0:
        purged = JobArchives.purge_old_archives(
            older_than_days=JOB_ARCHIVE_RETENTION_DAYS
        )
    return {
        "archived": archived,
        "purged": purged,
        "job_retention_days": JOB_RETENTION_DAYS,
        "job_archive_retention_days": JOB_ARCHIVE_RETENTION_DAYS,
    }


# ---------------------------------------------------------------------------
# Redis cache helpers
# ---------------------------------------------------------------------------

_JOB_CACHE_TTL = 10  # seconds


async def _cache_job(request: Request, job_id: str, job_data: dict) -> None:
    """Write job data to Redis (fire-and-forget)."""
    redis = getattr(request.app.state, "redis", None)
    if not redis:
        return
    try:
        key = f"job:{job_id}"
        await redis.set(key, json.dumps(job_data), ex=_JOB_CACHE_TTL)
    except Exception as e:
        log.debug(f"Redis cache write failed for job {job_id}: {e}")


async def _invalidate_job_cache(request: Request, job_id: str) -> None:
    """Remove a job from the Redis cache after a status change."""
    redis = getattr(request.app.state, "redis", None)
    if not redis:
        return
    try:
        await redis.delete(f"job:{job_id}")
    except Exception as e:
        log.debug(f"Redis cache invalidation failed for job {job_id}: {e}")


async def _get_cached_job(request: Request, job_id: str) -> Optional[dict]:
    redis = getattr(request.app.state, "redis", None)
    if not redis:
        return None
    try:
        data = await redis.get(f"job:{job_id}")
        return json.loads(data) if data else None
    except Exception as e:
        log.debug(f"Redis cache read failed for job {job_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


async def _run_job(request: Request, job_id: str, payload: dict, user) -> None:
    """
    Background task that drives a single job through its lifecycle:
        queued → running → completed | failed (with optional re-queue)
    """
    Jobs.update_job_running(job_id)
    await _invalidate_job_cache(request, job_id)

    try:
        # Force non-streaming so we get a plain JSON response dict
        payload = {**payload, "stream": False}
        response = await generate_chat_completion(request, form_data=payload, user=user)

        # generate_chat_completion may return a Response object or a dict
        if hasattr(response, "body"):
            result = json.loads(response.body)
        elif isinstance(response, dict):
            result = response
        else:
            # Last-resort: attempt JSON parse
            result = {"raw": str(response)}

        Jobs.update_job_completed(job_id, result=result)
        import time as _time
        _sse_publish(user.id, {"job_id": job_id, "status": "completed", "updated_at": int(_time.time())})
    except Exception as exc:
        log.exception(f"Job {job_id} failed: {exc}")
        Jobs.update_job_failed(job_id, error=str(exc), requeue=True)
        import time as _time
        _sse_publish(user.id, {"job_id": job_id, "status": "failed", "error": str(exc), "updated_at": int(_time.time())})
    finally:
        await _invalidate_job_cache(request, job_id)


# ---------------------------------------------------------------------------
# Endpoint helpers
# ---------------------------------------------------------------------------


def _to_response(job) -> dict:
    return JobResponse(
        job_id=job.id,
        status=job.status,
        model_id=job.model_id,
        backend_url=job.backend_url,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        created_at=job.created_at,
        updated_at=job.updated_at,
        result=job.result,
        error=job.error,
    ).model_dump()


# ---------------------------------------------------------------------------
# POST /chat/completions — Submit
# ---------------------------------------------------------------------------


@router.post(
    "/chat/completions",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an async chat-completion job",
    response_description="Job accepted. Poll GET /{job_id} for status.",
)
async def submit_job(
    request: Request,
    form_data: JobSubmitForm,
    user=Depends(get_verified_user),
):
    """
    Enqueue a chat-completion job.

    Returns **202 Accepted** immediately with `job_id` and `status=queued`.
    The client should then poll `GET /api/v1/jobs/{job_id}` to track progress.
    """
    models = request.app.state.MODELS
    if form_data.model not in models:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{form_data.model}' not found.",
        )

    # Build the payload we'll pass to generate_chat_completion
    payload = form_data.model_dump(exclude_none=True)
    payload["stream"] = False  # jobs always collect the full response

    job = Jobs.insert_new_job(
        user_id=user.id,
        model_id=form_data.model,
        request_payload=payload,
        priority=getattr(user, "job_priority", 5),  # Phase 2: per-user priority
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create job record.",
        )

    # Fire the background worker — results stored in DB, not in-memory
    await create_task(
        request.app.state.redis,
        _run_job(request, job.id, payload, user),
        id=job.id,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job.id,
            "status": JOB_STATUS_QUEUED,
            "model_id": job.model_id,
            "created_at": job.created_at,
        },
    )


# ---------------------------------------------------------------------------
# GET /{job_id} — Poll
# ---------------------------------------------------------------------------


@router.get(
    "/{job_id}",
    summary="Get job status and result",
)
async def get_job(
    request: Request,
    job_id: str,
    include_result: bool = Query(
        True,
        description="Set to false to omit the result payload (useful for polling).",
    ),
    user=Depends(get_verified_user),
):
    """
    Poll the status of an async job.

    - While running: `result` is `null`.
    - When `status=completed`: `result` contains the full chat-completion response.
    - When `status=failed`: `error` contains the failure message.
    """
    # Try Redis cache first (reduces DB load when clients poll frequently)
    cached = await _get_cached_job(request, job_id)
    if cached and include_result:
        if cached.get("user_id") != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return cached

    job = Jobs.get_job_by_id(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if job.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this job.",
        )

    response_data = _to_response(job)

    # Strip result if caller doesn't want it (saves bandwidth while polling)
    if not include_result:
        response_data["result"] = None

    # Cache completed/failed jobs (they won't change again)
    if job.status in TERMINAL_STATUSES and include_result:
        await _cache_job(request, job_id, response_data)

    return response_data


# ---------------------------------------------------------------------------
# DELETE /{job_id} — Cancel
# ---------------------------------------------------------------------------


@router.delete(
    "/{job_id}",
    summary="Cancel a queued or running job",
)
async def cancel_job(
    request: Request,
    job_id: str,
    user=Depends(get_verified_user),
):
    """
    Cancel a job. If the job is already in a terminal state (completed, failed,
    or cancelled) it is returned as-is without error.
    """
    job = Jobs.get_job_by_id(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if job.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to cancel this job.",
        )

    # Also try to stop the underlying asyncio task (best-effort)
    await stop_item_tasks(request.app.state.redis, job_id)

    updated = Jobs.update_job_cancelled(job_id)
    await _invalidate_job_cache(request, job_id)

    return _to_response(updated)


# ---------------------------------------------------------------------------
# GET / — List
# ---------------------------------------------------------------------------


@router.get(
    "/",
    summary="List current user's jobs",
)
async def list_jobs(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="Filter by status"),
    model_id: Optional[str] = Query(None, description="Filter by model ID"),
    user=Depends(get_verified_user),
):
    """
    Return a paginated list of the authenticated user's jobs,
    ordered newest first.  Supports optional `status` and `model_id` filters.
    """
    jobs = Jobs.get_jobs_by_user_id(
        user.id, skip=skip, limit=limit, status=status, model_id=model_id
    )
    total = Jobs.count_jobs_by_user_id(user.id)
    return {
        "jobs": [_to_response(j) for j in jobs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# GET /admin/list  — Admin: list all jobs with filters
# ---------------------------------------------------------------------------


@router.get(
    "/admin/list",
    summary="Admin: list all jobs with optional filters",
)
async def admin_list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    user=Depends(get_admin_user),
):
    """Admin view: all jobs, filterable by status / model_id / user_id."""
    jobs = Jobs.get_jobs_admin(
        skip=skip, limit=limit, status=status, model_id=model_id, user_id=user_id
    )
    total = Jobs.count_jobs_admin(status=status, model_id=model_id, user_id=user_id)
    return {
        "jobs": [_to_response(j) for j in jobs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# POST /{job_id}/retry  — Admin: re-queue a terminal job
# ---------------------------------------------------------------------------


@router.post(
    "/{job_id}/retry",
    summary="Retry a failed or cancelled job (admin only)",
)
async def retry_job(
    request: Request,
    job_id: str,
    user=Depends(get_admin_user),
):
    """
    Reset a terminal (failed / cancelled) job back to QUEUED so the
    scheduler picks it up again.  Clears `error`, resets `attempt_count`
    to 0. The job must exist and be in a terminal state.
    """
    job = Jobs.get_job_by_id(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    if job.status not in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' is in state '{job.status}' — only terminal jobs can be retried.",
        )

    updated = Jobs.retry_job(job_id)
    await _invalidate_job_cache(request, job_id)
    return _to_response(updated)
