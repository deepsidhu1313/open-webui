"""
models/jobs.py — ORM model, Pydantic schema, and data-access layer for the
async job queue API.

Status lifecycle:
    queued → running → completed
                    ↘ failed (re-queue if attempt_count < max_attempts)
    queued / running → cancelled (terminal, no retry)
"""

import time
import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    Index,
    Integer,
    Text,
    JSON,
)
from sqlalchemy.orm import Session

from open_webui.internal.db import Base, get_db_context

####################
# DB Schema
####################

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = {JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED}


class Job(Base):
    __tablename__ = "job"

    id = Column(Text, primary_key=True, nullable=False)
    user_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default=JOB_STATUS_QUEUED)

    # Priority (Phase 2 — scheduler)
    priority = Column(Integer, nullable=False, default=5)
    priority_score = Column(Float, nullable=False, default=5.0)

    # Backend tracking
    model_id = Column(Text, nullable=True)
    backend_url = Column(Text, nullable=True)

    # Payload / result / error
    request = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    # Retry counters
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)

    # Timestamps (epoch seconds)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("job_user_id_idx", "user_id"),
        Index("job_user_status_idx", "user_id", "status"),
        Index("job_created_at_idx", "created_at"),
        Index("job_status_priority_score_idx", "status", "priority_score"),
    )


####################
# Pydantic Models
####################


class JobModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    status: str

    priority: int = 5
    priority_score: float = 5.0

    model_id: Optional[str] = None
    backend_url: Optional[str] = None

    request: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None

    attempt_count: int = 0
    max_attempts: int = 3

    created_at: int
    updated_at: int


####################
# Forms / Responses
####################


class JobSubmitForm(BaseModel):
    """Accepted body for POST /api/v1/jobs/chat/completions"""

    model: str
    messages: list[dict]
    # Optional standard OpenAI-compat params
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False  # always False for jobs — we collect the full result


class JobResponse(BaseModel):
    """Returned by GET /api/v1/jobs/{job_id} and POST submit"""

    job_id: str
    status: str
    model_id: Optional[str] = None
    backend_url: Optional[str] = None
    attempt_count: int
    max_attempts: int
    created_at: int
    updated_at: int
    result: Optional[dict] = None
    error: Optional[str] = None


####################
# Data Access Layer
####################


class JobsTable:
    def insert_new_job(
        self,
        user_id: str,
        model_id: str,
        request_payload: dict,
        priority: int = 5,
        max_attempts: int = 3,
        db: Optional[Session] = None,
    ) -> Optional[JobModel]:
        """Create a new job record in QUEUED state and return it."""
        with get_db_context(db) as db:
            now = int(time.time())
            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                user_id=user_id,
                status=JOB_STATUS_QUEUED,
                priority=priority,
                priority_score=float(priority),
                model_id=model_id,
                backend_url=None,
                request=request_payload,
                result=None,
                error=None,
                attempt_count=0,
                max_attempts=max_attempts,
                created_at=now,
                updated_at=now,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return JobModel.model_validate(job)

    def get_job_by_id(
        self, job_id: str, db: Optional[Session] = None
    ) -> Optional[JobModel]:
        with get_db_context(db) as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            return JobModel.model_validate(job) if job else None

    def get_jobs_by_user_id(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        model_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> list[JobModel]:
        with get_db_context(db) as db:
            query = (
                db.query(Job)
                .filter(Job.user_id == user_id)
                .order_by(Job.created_at.desc())
            )
            if status:
                query = query.filter(Job.status == status)
            if model_id:
                query = query.filter(Job.model_id == model_id)
            if skip:
                query = query.offset(skip)
            if limit:
                query = query.limit(limit)
            return [JobModel.model_validate(j) for j in query.all()]

    def get_jobs_admin(
        self,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        model_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> list[JobModel]:
        """Admin-only: list all jobs with optional filters."""
        with get_db_context(db) as db:
            query = db.query(Job).order_by(Job.created_at.desc())
            if status:
                query = query.filter(Job.status == status)
            if model_id:
                query = query.filter(Job.model_id == model_id)
            if user_id:
                query = query.filter(Job.user_id == user_id)
            return [JobModel.model_validate(j) for j in query.offset(skip).limit(limit).all()]

    def count_jobs_admin(
        self,
        status: Optional[str] = None,
        model_id: Optional[str] = None,
        user_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> int:
        """Count all jobs (admin) with optional filters."""
        with get_db_context(db) as db:
            query = db.query(Job)
            if status:
                query = query.filter(Job.status == status)
            if model_id:
                query = query.filter(Job.model_id == model_id)
            if user_id:
                query = query.filter(Job.user_id == user_id)
            return query.count()

    def count_jobs_by_user_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> int:
        with get_db_context(db) as db:
            return db.query(Job).filter(Job.user_id == user_id).count()

    def update_job_running(
        self,
        job_id: str,
        backend_url: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Optional[JobModel]:
        """Mark a job as RUNNING and record which backend is handling it."""
        with get_db_context(db) as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            job.status = JOB_STATUS_RUNNING
            job.attempt_count = job.attempt_count + 1
            if backend_url:
                job.backend_url = backend_url
            job.updated_at = int(time.time())
            db.commit()
            db.refresh(job)
            return JobModel.model_validate(job)

    def update_job_completed(
        self, job_id: str, result: dict, db: Optional[Session] = None
    ) -> Optional[JobModel]:
        """Mark a job as COMPLETED and store the result."""
        with get_db_context(db) as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            job.status = JOB_STATUS_COMPLETED
            job.result = result
            job.error = None
            job.updated_at = int(time.time())
            db.commit()
            db.refresh(job)
            return JobModel.model_validate(job)

    def update_job_failed(
        self,
        job_id: str,
        error: str,
        requeue: bool = False,
        db: Optional[Session] = None,
    ) -> Optional[JobModel]:
        """
        Mark a job as FAILED.
        If ``requeue=True`` and ``attempt_count < max_attempts``, move it back
        to QUEUED so the scheduler can retry it.
        """
        with get_db_context(db) as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            job.error = error
            if requeue and job.attempt_count < job.max_attempts:
                job.status = JOB_STATUS_QUEUED
            else:
                job.status = JOB_STATUS_FAILED
            job.updated_at = int(time.time())
            db.commit()
            db.refresh(job)
            return JobModel.model_validate(job)

    def update_job_cancelled(
        self, job_id: str, db: Optional[Session] = None
    ) -> Optional[JobModel]:
        """Cancel a job. Terminal — no retry."""
        with get_db_context(db) as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            if job.status in TERMINAL_STATUSES:
                # Already terminal — return as-is
                return JobModel.model_validate(job)
            job.status = JOB_STATUS_CANCELLED
            job.updated_at = int(time.time())
            db.commit()
            db.refresh(job)
            return JobModel.model_validate(job)

    def retry_job(
        self, job_id: str, db: Optional[Session] = None
    ) -> Optional[JobModel]:
        """
        Admin-only: Reset a terminal job back to QUEUED so the scheduler
        picks it up again.  Clears error, resets attempt_count to 0 and
        priority_score back to the base priority.
        """
        with get_db_context(db) as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            job.status = JOB_STATUS_QUEUED
            job.error = None
            job.attempt_count = 0
            job.priority_score = float(job.priority)
            job.updated_at = int(time.time())
            db.commit()
            db.refresh(job)
            return JobModel.model_validate(job)

    def delete_job_by_id(
        self, job_id: str, db: Optional[Session] = None
    ) -> bool:
        try:
            with get_db_context(db) as db:
                db.query(Job).filter(Job.id == job_id).delete()
                db.commit()
                return True
        except Exception:
            return False

    def get_job_analytics(self, db: Optional[Session] = None) -> dict:
        """
        Aggregate job statistics for the admin analytics panel.
        Returns counts by status, by model, avg wait time, success rate.
        """
        import time
        from sqlalchemy import func, case

        with get_db_context(db) as db:
            # Overall counts by status
            status_rows = (
                db.query(Job.status, func.count(Job.id).label("count"))
                .group_by(Job.status)
                .all()
            )
            by_status = {row.status: row.count for row in status_rows}

            total = sum(by_status.values())
            completed = by_status.get(JOB_STATUS_COMPLETED, 0)
            failed = by_status.get(JOB_STATUS_FAILED, 0)
            success_rate = round(completed / total * 100, 1) if total > 0 else 0.0

            # By model
            model_rows = (
                db.query(
                    Job.model_id,
                    func.count(Job.id).label("total"),
                    func.sum(
                        case((Job.status == JOB_STATUS_COMPLETED, 1), else_=0)
                    ).label("completed"),
                    func.sum(
                        case((Job.status == JOB_STATUS_FAILED, 1), else_=0)
                    ).label("failed"),
                )
                .filter(Job.model_id.isnot(None))
                .group_by(Job.model_id)
                .order_by(func.count(Job.id).desc())
                .limit(20)
                .all()
            )
            by_model = [
                {
                    "model_id": r.model_id,
                    "total": r.total,
                    "completed": r.completed,
                    "failed": r.failed,
                }
                for r in model_rows
            ]

            # Average wait time: avg(updated_at - created_at) for completed jobs
            avg_wait_result = (
                db.query(
                    func.avg(Job.updated_at - Job.created_at).label("avg_wait")
                )
                .filter(Job.status == JOB_STATUS_COMPLETED)
                .first()
            )
            avg_wait_s = round(avg_wait_result.avg_wait or 0.0, 1)

            return {
                "total": total,
                "by_status": by_status,
                "success_rate": success_rate,
                "avg_wait_seconds": avg_wait_s,
                "by_model": by_model,
            }


Jobs = JobsTable()


####################
# Archive ORM + DAL
####################


class JobArchive(Base):
    """Long-term storage for jobs that have aged out of the active `job` table."""

    __tablename__ = "job_archive"

    id = Column(Text, primary_key=True, nullable=False)
    user_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False)

    priority = Column(Integer, nullable=False, default=5)
    priority_score = Column(Float, nullable=False, default=5.0)

    model_id = Column(Text, nullable=True)
    backend_url = Column(Text, nullable=True)

    request = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    archived_at = Column(BigInteger, nullable=False)  # epoch seconds when archived

    __table_args__ = (
        Index("job_archive_user_id_idx", "user_id"),
        Index("job_archive_status_idx", "status"),
        Index("job_archive_created_at_idx", "created_at"),
        Index("job_archive_archived_at_idx", "archived_at"),
    )


class JobArchiveModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    status: str

    priority: int = 5
    priority_score: float = 5.0

    model_id: Optional[str] = None
    backend_url: Optional[str] = None

    request: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None

    attempt_count: int = 0
    max_attempts: int = 3

    created_at: int
    updated_at: int
    archived_at: int


class JobArchiveTable:
    # ------------------------------------------------------------------
    # Archive / purge helpers called by the scheduler
    # ------------------------------------------------------------------

    def archive_old_jobs(
        self,
        older_than_days: int = 30,
        db: Optional[Session] = None,
    ) -> int:
        """
        Move terminal jobs older than ``older_than_days`` from ``job`` →
        ``job_archive`` in a single transaction.

        Returns the number of rows archived.
        """
        cutoff = int(time.time()) - older_than_days * 86_400
        now = int(time.time())
        archived = 0

        try:
            with get_db_context(db) as db:
                old_jobs = (
                    db.query(Job)
                    .filter(
                        Job.status.in_(TERMINAL_STATUSES),
                        Job.updated_at < cutoff,
                    )
                    .all()
                )
                for job in old_jobs:
                    row = JobArchive(
                        id=job.id,
                        user_id=job.user_id,
                        status=job.status,
                        priority=job.priority,
                        priority_score=job.priority_score,
                        model_id=job.model_id,
                        backend_url=job.backend_url,
                        request=job.request,
                        result=job.result,
                        error=job.error,
                        attempt_count=job.attempt_count,
                        max_attempts=job.max_attempts,
                        created_at=job.created_at,
                        updated_at=job.updated_at,
                        archived_at=now,
                    )
                    db.add(row)
                    db.delete(job)
                archived = len(old_jobs)
                db.commit()
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).error(f"archive_old_jobs failed: {e}")

        return archived

    def purge_old_archives(
        self,
        older_than_days: int,
        db: Optional[Session] = None,
    ) -> int:
        """
        Hard-delete rows from ``job_archive`` that were archived more than
        ``older_than_days`` ago.  Pass 0 to disable.

        Returns the number of rows deleted.
        """
        if older_than_days <= 0:
            return 0

        cutoff = int(time.time()) - older_than_days * 86_400
        deleted = 0
        try:
            with get_db_context(db) as db:
                deleted = (
                    db.query(JobArchive)
                    .filter(JobArchive.archived_at < cutoff)
                    .delete(synchronize_session=False)
                )
                db.commit()
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).error(f"purge_old_archives failed: {e}")

        return deleted

    # ------------------------------------------------------------------
    # Query helpers for admin / user APIs
    # ------------------------------------------------------------------

    def get_archived_jobs(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        model_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
        db: Optional[Session] = None,
    ) -> list[JobArchiveModel]:
        with get_db_context(db) as db:
            q = db.query(JobArchive)
            if user_id:
                q = q.filter(JobArchive.user_id == user_id)
            if status:
                q = q.filter(JobArchive.status == status)
            if model_id:
                q = q.filter(JobArchive.model_id == model_id)
            q = q.order_by(JobArchive.archived_at.desc())
            if skip:
                q = q.offset(skip)
            if limit:
                q = q.limit(limit)
            return [JobArchiveModel.model_validate(r) for r in q.all()]

    def count_archived_jobs(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> int:
        with get_db_context(db) as db:
            q = db.query(JobArchive)
            if user_id:
                q = q.filter(JobArchive.user_id == user_id)
            if status:
                q = q.filter(JobArchive.status == status)
            return q.count()

    def get_combined_analytics(self, db: Optional[Session] = None) -> dict:
        """
        Union job + job_archive for all-time analytics.

        Returns: total, by_status, success_rate, avg_wait_seconds,
                 by_model (top 20), by_user (top 20), daily_history (90d),
                 includes_archive: True
        """
        from sqlalchemy import func, case, union_all, select
        import datetime as _dt

        with get_db_context(db) as db:
            def _table_select(model):
                return select(
                    model.status,
                    model.user_id,
                    model.model_id,
                    model.created_at,
                    model.updated_at,
                )

            combined = union_all(
                _table_select(Job),
                _table_select(JobArchive),
            ).subquery()

            # Total + by-status
            total = db.query(func.count()).select_from(combined).scalar() or 0
            status_rows = (
                db.query(combined.c.status, func.count().label("count"))
                .group_by(combined.c.status).all()
            )
            by_status = {r.status: r.count for r in status_rows}
            completed_count = by_status.get(JOB_STATUS_COMPLETED, 0)
            success_rate = round(completed_count / total * 100, 1) if total > 0 else 0.0

            # By model (top 20)
            model_rows = (
                db.query(
                    combined.c.model_id,
                    func.count().label("total"),
                    func.sum(case((combined.c.status == JOB_STATUS_COMPLETED, 1), else_=0)).label("completed"),
                    func.sum(case((combined.c.status == JOB_STATUS_FAILED, 1), else_=0)).label("failed"),
                )
                .filter(combined.c.model_id.isnot(None))
                .group_by(combined.c.model_id)
                .order_by(func.count().desc())
                .limit(20).all()
            )
            by_model = [
                {"model_id": r.model_id, "total": r.total, "completed": r.completed, "failed": r.failed}
                for r in model_rows
            ]

            # By user (top 20)
            user_rows = (
                db.query(
                    combined.c.user_id,
                    func.count().label("total"),
                    func.sum(case((combined.c.status == JOB_STATUS_COMPLETED, 1), else_=0)).label("completed"),
                    func.sum(case((combined.c.status == JOB_STATUS_FAILED, 1), else_=0)).label("failed"),
                    func.sum(case((combined.c.status == JOB_STATUS_CANCELLED, 1), else_=0)).label("cancelled"),
                )
                .filter(combined.c.user_id.isnot(None))
                .group_by(combined.c.user_id)
                .order_by(func.count().desc())
                .limit(20).all()
            )
            by_user_raw = [
                {"user_id": r.user_id, "total": r.total, "completed": r.completed,
                 "failed": r.failed, "cancelled": r.cancelled}
                for r in user_rows
            ]

            # Resolve user_id -> name + email via Users table
            try:
                from open_webui.models.users import Users
                user_ids = [u["user_id"] for u in by_user_raw]
                user_details = {
                    u.id: {"name": u.name, "email": u.email}
                    for u in (Users.get_users_by_user_ids(user_ids) if user_ids else [])
                }
            except Exception:
                user_details = {}

            by_user = [
                {
                    **u,
                    "name": user_details.get(u["user_id"], {}).get("name"),
                    "email": user_details.get(u["user_id"], {}).get("email"),
                }
                for u in by_user_raw
            ]

            # Daily history — last 90 days, SQLite-compatible (C1)
            day_secs = 86_400
            cutoff_90d = int(time.time()) - 90 * day_secs

            # Detect DB dialect for date bucketing
            try:
                dialect = db.get_bind().dialect.name
            except Exception:
                dialect = "unknown"

            if dialect == "sqlite":
                # SQLite: use strftime to bucket by date string
                from sqlalchemy import text as sa_text
                day_label = func.strftime(
                    "%Y-%m-%d",
                    func.datetime(combined.c.created_at, "unixepoch")
                ).label("day_bucket")
                daily_rows = (
                    db.query(
                        day_label,
                        func.count().label("total"),
                        func.sum(case((combined.c.status == JOB_STATUS_COMPLETED, 1), else_=0)).label("completed"),
                        func.sum(case((combined.c.status == JOB_STATUS_FAILED, 1), else_=0)).label("failed"),
                    )
                    .filter(combined.c.created_at >= cutoff_90d)
                    .group_by(day_label)
                    .order_by(day_label)
                    .all()
                )
                daily_history = [
                    {
                        "date": r.day_bucket,
                        "total": r.total,
                        "completed": r.completed,
                        "failed": r.failed,
                    }
                    for r in daily_rows
                ]
            else:
                # PostgreSQL / MySQL: integer-divide epoch by seconds-per-day
                daily_rows = (
                    db.query(
                        (combined.c.created_at / day_secs).label("day_bucket"),
                        func.count().label("total"),
                        func.sum(case((combined.c.status == JOB_STATUS_COMPLETED, 1), else_=0)).label("completed"),
                        func.sum(case((combined.c.status == JOB_STATUS_FAILED, 1), else_=0)).label("failed"),
                    )
                    .filter(combined.c.created_at >= cutoff_90d)
                    .group_by("day_bucket")
                    .order_by("day_bucket")
                    .all()
                )
                daily_history = [
                    {
                        "date": _dt.date.fromtimestamp(int(r.day_bucket) * day_secs).isoformat(),
                        "total": r.total,
                        "completed": r.completed,
                        "failed": r.failed,
                    }
                    for r in daily_rows
                ]

            # Avg wait (completed jobs)
            avg_wait = (
                db.query(func.avg(combined.c.updated_at - combined.c.created_at))
                .filter(combined.c.status == JOB_STATUS_COMPLETED)
                .scalar()
            )

            return {
                "total": total,
                "by_status": by_status,
                "success_rate": success_rate,
                "avg_wait_seconds": round(avg_wait or 0.0, 1),
                "by_model": by_model,
                "by_user": by_user,
                "daily_history": daily_history,
                "includes_archive": True,
            }


JobArchives = JobArchiveTable()
