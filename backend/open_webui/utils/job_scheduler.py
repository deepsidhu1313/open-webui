"""
utils/job_scheduler.py — Background priority-based job scheduler with retry
and anti-starvation support.

Design:
  - A long-running asyncio loop (`run_scheduler`) picks the highest-priority
    queued job (`priority_score DESC`) every TICK seconds.
  - Concurrency is bounded to MAX_CONCURRENT_JOBS at once.
  - Every STARVATION_TICK seconds, waiting jobs get their priority_score
    bumped by STARVATION_INCREMENT — so even low-priority jobs eventually run.
  - Failed jobs are retried (up to max_attempts) with exponential backoff
    implemented via the `attempt_count` field already in the job table.

Usage (in main.py lifespan):
    from open_webui.utils.job_scheduler import start_scheduler, stop_scheduler
    await start_scheduler(app)   # on startup
    await stop_scheduler(app)    # on shutdown
"""

import asyncio
import logging
import os
import time
from typing import Optional

from sqlalchemy import update

from open_webui.models.jobs import Jobs, JobArchives, Job, JOB_STATUS_QUEUED, JOB_STATUS_RUNNING
from open_webui.internal.db import get_db_context

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration  (all tunable via env vars)
# ---------------------------------------------------------------------------

SCHEDULER_TICK_SECONDS = 2           # how often the loop checks for queued jobs
STARVATION_TICK_SECONDS = 30          # how often to bump waiting jobs' priority_score
STARVATION_INCREMENT = 0.5            # score added per starvation tick
MAX_CONCURRENT_JOBS = 10              # max simultaneously running job workers

# Retention / archive policy
JOB_RETENTION_DAYS = int(os.getenv("JOB_RETENTION_DAYS", "30"))
"""Days after which a terminal job is moved from `job` → `job_archive`."""

JOB_ARCHIVE_RETENTION_DAYS = int(os.getenv("JOB_ARCHIVE_RETENTION_DAYS", "365"))
"""Days after which an archived row is hard-deleted.  Set to 0 to disable."""

ARCHIVE_CHECK_INTERVAL_SECONDS = 3_600  # run archive sweep once per hour

# Backend snapshot policy
SNAPSHOT_INTERVAL_SECONDS = int(os.getenv("BACKEND_SNAPSHOT_INTERVAL", "300"))  # every 5 min
SNAPSHOT_RETENTION_DAYS = int(os.getenv("BACKEND_SNAPSHOT_RETENTION_DAYS", "7"))  # keep 7 days

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_scheduler_task: Optional[asyncio.Task] = None
_starvation_task: Optional[asyncio.Task] = None
_archive_task: Optional[asyncio.Task] = None
_snapshot_task: Optional[asyncio.Task] = None
_semaphore: Optional[asyncio.Semaphore] = None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _claim_next_queued_job():
    """
    Atomically fetch-and-mark-running the highest-priority queued job.

    Returns the job ID if one was claimed, otherwise None.
    This must be called inside a DB session acquired by the caller.
    """
    try:
        with get_db_context() as db:
            job = (
                db.query(Job)
                .filter(Job.status == JOB_STATUS_QUEUED)
                .order_by(Job.priority_score.desc(), Job.created_at.asc())
                .with_for_update(skip_locked=True)   # postgres-compatible advisory lock
                .first()
            )
            if job is None:
                return None

            job.status = JOB_STATUS_RUNNING
            job.attempt_count = job.attempt_count + 1
            job.updated_at = int(time.time())
            db.commit()
            return job.id
    except Exception as e:
        # SQLite doesn't support SKIP LOCKED; fall back to a plain query
        try:
            with get_db_context() as db:
                job = (
                    db.query(Job)
                    .filter(Job.status == JOB_STATUS_QUEUED)
                    .order_by(Job.priority_score.desc(), Job.created_at.asc())
                    .first()
                )
                if job is None:
                    return None
                job.status = JOB_STATUS_RUNNING
                job.attempt_count = job.attempt_count + 1
                job.updated_at = int(time.time())
                db.commit()
                return job.id
        except Exception as inner:
            log.error(f"Scheduler: failed to claim job: {inner}")
            return None


def _bump_stale_jobs():
    """Increment priority_score for all jobs still queued (anti-starvation)."""
    try:
        with get_db_context() as db:
            db.execute(
                update(Job)
                .where(Job.status == JOB_STATUS_QUEUED)
                .values(priority_score=Job.priority_score + STARVATION_INCREMENT)
            )
            db.commit()
    except Exception as e:
        log.error(f"Scheduler: starvation bump failed: {e}")


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

async def _execute_job(request, job_id: str, user_stub) -> None:
    """
    Run a single job end-to-end.  On success → completed.
    On failure → failed or re-queued (if attempts remain).
    """
    from open_webui.utils.chat import generate_chat_completion
    import json

    job = Jobs.get_job_by_id(job_id)
    if job is None:
        return

    payload = dict(job.request or {})
    payload["stream"] = False

    try:
        response = await generate_chat_completion(
            request, form_data=payload, user=user_stub
        )

        if hasattr(response, "body"):
            result = json.loads(response.body)
        elif isinstance(response, dict):
            result = response
        else:
            result = {"raw": str(response)}

        Jobs.update_job_completed(job_id, result=result)
        log.info(f"Scheduler: job {job_id} completed")

    except Exception as exc:
        log.error(f"Scheduler: job {job_id} failed (attempt {job.attempt_count}): {exc}")
        Jobs.update_job_failed(job_id, error=str(exc), requeue=True)


# ---------------------------------------------------------------------------
# Scheduler loops
# ---------------------------------------------------------------------------

async def _scheduler_loop(app) -> None:
    """Main loop: claim and dispatch queued jobs up to MAX_CONCURRENT_JOBS."""
    global _semaphore
    _semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    while True:
        try:
            job_id = _claim_next_queued_job()
            if job_id:
                async with _semaphore:
                    # Create a minimal user stub matching the job's user_id
                    from open_webui.models.users import Users
                    job = Jobs.get_job_by_id(job_id)
                    user_stub = Users.get_user_by_id(job.user_id) if job else None

                    if user_stub:
                        asyncio.create_task(
                            _execute_job(
                                _make_request(app), job_id, user_stub
                            )
                        )
                    else:
                        Jobs.update_job_failed(
                            job_id, error="User not found", requeue=False
                        )
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Scheduler loop error: {e}")

        await asyncio.sleep(SCHEDULER_TICK_SECONDS)


async def _starvation_loop() -> None:
    """Periodically bump waiting jobs so they don't starve forever."""
    while True:
        try:
            await asyncio.sleep(STARVATION_TICK_SECONDS)
            _bump_stale_jobs()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Starvation loop error: {e}")


async def _archive_loop() -> None:
    """
    Hourly maintenance loop:
    1. Move terminal jobs older than JOB_RETENTION_DAYS → job_archive.
    2. Hard-delete archive rows older than JOB_ARCHIVE_RETENTION_DAYS
       (skipped when JOB_ARCHIVE_RETENTION_DAYS == 0).
    """
    while True:
        try:
            await asyncio.sleep(ARCHIVE_CHECK_INTERVAL_SECONDS)
            archived = JobArchives.archive_old_jobs(older_than_days=JOB_RETENTION_DAYS)
            if archived:
                log.info(f"Archive: moved {archived} job(s) to job_archive")

            if JOB_ARCHIVE_RETENTION_DAYS > 0:
                purged = JobArchives.purge_old_archives(
                    older_than_days=JOB_ARCHIVE_RETENTION_DAYS
                )
                if purged:
                    log.info(f"Archive: purged {purged} old archive row(s)")
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Archive loop error: {e}")


async def _snapshot_loop(app) -> None:
    """
    B2: Periodic backend metrics snapshot loop.

    Every SNAPSHOT_INTERVAL_SECONDS seconds:
    1. Collect psutil CPU/RAM for the WebUI host.
    2. Count active/queued jobs from the DB.
    3. For each configured Ollama backend, call /api/ps to get loaded models
       and VRAM usage.
    4. Persist one BackendSnapshot row per backend.
    5. Purge rows older than SNAPSHOT_RETENTION_DAYS once per day.
    """
    from open_webui.models.backend_snapshots import BackendSnapshots
    import aiohttp
    import psutil

    last_purge_day = -1

    while True:
        try:
            await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)

            now = int(time.time())

            # 1. System metrics
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent

            # 2. Job queue depth
            try:
                with get_db_context() as db:
                    active = db.query(Job).filter(Job.status == JOB_STATUS_RUNNING).count()
                    queued = db.query(Job).filter(Job.status == JOB_STATUS_QUEUED).count()
            except Exception:
                active = queued = None

            # 3. Resolve backend URLs from app config
            ollama_enabled = getattr(
                getattr(app.state, "config", None), "ENABLE_OLLAMA_API", False
            )
            backend_urls = getattr(
                getattr(app.state, "config", None), "OLLAMA_BASE_URLS", []
            ) if ollama_enabled else []

            if not backend_urls:
                backend_urls = ["__local__"]  # placeholder when no Ollama

            for url in backend_urls:
                loaded_models = None
                vram_gb = None

                if url != "__local__":
                    try:
                        api_url = f"{url.rstrip('/')}/api/ps"
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                api_url, timeout=aiohttp.ClientTimeout(total=3)
                            ) as resp:
                                if resp.status == 200:
                                    ps = await resp.json()
                                    models = ps.get("models", [])
                                    loaded_models = len(models)
                                    vram_gb = round(
                                        sum(
                                            # On Apple Silicon, size_vram=0 (unified memory).
                                            # Fall back to total model size in that case.
                                            m.get("size_vram") or m.get("size", 0)
                                            for m in models
                                        ) / 1_073_741_824,
                                        2,
                                    )
                    except Exception:
                        pass  # backend unreachable — still record host metrics

                BackendSnapshots.insert(
                    {
                        "captured_at": now,
                        "backend_url": url,
                        "cpu_percent": cpu,
                        "ram_percent": ram,
                        "active_jobs": active,
                        "queued_jobs": queued,
                        "loaded_models": loaded_models,
                        "vram_used_gb": vram_gb,
                        "avg_tokens_per_second": None,  # populated externally if available
                    }
                )

            # 4. Daily purge
            today = now // 86_400
            if today != last_purge_day:
                try:
                    n = BackendSnapshots.purge_old(older_than_days=SNAPSHOT_RETENTION_DAYS)
                    if n:
                        log.info(f"Snapshot: purged {n} old row(s)")
                    last_purge_day = today
                except Exception as e:
                    log.warning(f"Snapshot purge failed: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Snapshot loop error: {e}")


def _make_request(app):
    """Build a minimal Request-like object that generate_chat_completion expects."""
    from fastapi import Request
    from starlette.datastructures import Headers

    return Request(
        {
            "type": "http",
            "asgi.version": "3.0",
            "asgi.spec_version": "2.0",
            "method": "POST",
            "path": "/internal",
            "query_string": b"",
            "headers": Headers({}).raw,
            "client": ("127.0.0.1", 0),
            "server": ("127.0.0.1", 80),
            "scheme": "http",
            "app": app,
        }
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def start_scheduler(app) -> None:
    """Start the scheduler, starvation, and archive background tasks."""
    global _scheduler_task, _starvation_task, _archive_task, _snapshot_task

    if _scheduler_task and not _scheduler_task.done():
        return  # already running

    log.info(
        f"Job scheduler starting "
        f"(retention={JOB_RETENTION_DAYS}d, "
        f"archive_retention={'∞' if JOB_ARCHIVE_RETENTION_DAYS == 0 else str(JOB_ARCHIVE_RETENTION_DAYS) + 'd'})…"
    )
    _scheduler_task = asyncio.create_task(_scheduler_loop(app))
    _starvation_task = asyncio.create_task(_starvation_loop())
    _archive_task = asyncio.create_task(_archive_loop())
    _snapshot_task = asyncio.create_task(_snapshot_loop(app))


async def stop_scheduler() -> None:
    """Cancel the scheduler gracefully on shutdown."""
    global _scheduler_task, _starvation_task, _archive_task, _snapshot_task

    for task in (_scheduler_task, _starvation_task, _archive_task, _snapshot_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    log.info("Job scheduler stopped.")
