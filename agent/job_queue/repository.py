from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import QueueJobModel
from job_queue.schemas import JobStatus, JobType
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, utcnow


class QueueRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        job_type: JobType,
        payload: dict,
        *,
        delay_seconds: int = 0,
        max_attempts: int = 3,
        commit: bool = True,
    ) -> QueueJobModel:
        model = QueueJobModel(
            id=new_id("job"),
            type=job_type.value,
            payload=payload,
            status=JobStatus.QUEUED.value,
            attempts=0,
            max_attempts=max_attempts,
            run_after=utcnow() + timedelta(seconds=delay_seconds),
        )
        self.session.add(model)
        if commit:
            self.session.commit()
            self.session.refresh(model)
        else:
            self.session.flush()
        return model

    def enqueue_once(
        self,
        job_type: JobType,
        payload: dict,
        *,
        dedupe_key: str,
        max_attempts: int = 3,
        commit: bool = True,
    ) -> QueueJobModel:
        active = list(
            self.session.scalars(
                select(QueueJobModel).where(
                    QueueJobModel.type == job_type.value,
                    QueueJobModel.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                )
            )
        )
        for job in active:
            if job.payload.get("dedupe_key") == dedupe_key:
                return job
        return self.enqueue(
            job_type,
            {**payload, "dedupe_key": dedupe_key},
            max_attempts=max_attempts,
            commit=commit,
        )

    def claim_next(self) -> QueueJobModel | None:
        statement = (
            select(QueueJobModel)
            .where(QueueJobModel.status == JobStatus.QUEUED.value)
            .where(QueueJobModel.run_after <= utcnow())
            .order_by(QueueJobModel.created_at)
            .limit(1)
        )
        job = self.session.scalar(statement)
        if job is None:
            return None
        job.status = JobStatus.RUNNING.value
        job.attempts += 1
        self.session.commit()
        self.session.refresh(job)
        return job

    def complete(self, job_id: str) -> QueueJobModel:
        job = self._get(job_id)
        job.status = JobStatus.COMPLETED.value
        job.completed_at = utcnow()
        self.session.commit()
        self.session.refresh(job)
        return job

    def fail(
        self,
        job_id: str,
        error: str,
        *,
        retry_delay_seconds: int | None = None,
    ) -> QueueJobModel:
        job = self._get(job_id)
        if job.status != JobStatus.RUNNING.value:
            raise ConflictError("only running jobs can fail", {"job_id": job_id, "status": job.status})
        job.last_error = error
        if job.attempts < job.max_attempts:
            job.status = JobStatus.QUEUED.value
            delay = retry_delay_seconds if retry_delay_seconds is not None else 30 * job.attempts
            job.run_after = utcnow() + timedelta(seconds=delay)
        else:
            job.status = JobStatus.FAILED.value
        self.session.commit()
        self.session.refresh(job)
        return job

    def _get(self, job_id: str) -> QueueJobModel:
        job = self.session.get(QueueJobModel, job_id)
        if job is None:
            raise NotFoundError("job not found", {"job_id": job_id})
        return job
