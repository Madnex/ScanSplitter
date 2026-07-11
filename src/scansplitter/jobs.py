"""Background job execution and lifecycle management."""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


class JobCancelled(Exception):
    """Raised by cooperative workers when cancellation was requested."""


@dataclass
class Job:
    """Mutable state for one background operation."""

    job_id: str
    kind: str
    status: str
    progress: int
    stage: str | None
    result: dict[str, Any] | None
    error: str | None
    session_id: str
    created_at: float
    updated_at: float
    cancel_flag: threading.Event = field(default_factory=threading.Event, repr=False)
    download_bytes: bytes | None = field(default=None, repr=False)


class JobRegistry:
    """Thread-safe in-memory registry with idle-time cleanup."""

    def __init__(self, max_age_seconds: float = 3600) -> None:
        self.max_age_seconds = max_age_seconds
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str, session_id: str) -> Job:
        now = time.time()
        job = Job(
            job_id=uuid.uuid4().hex,
            kind=kind,
            status="queued",
            progress=0,
            stage=None,
            result=None,
            error=None,
            session_id=session_id,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._cleanup_locked(now)
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        now = time.time()
        with self._lock:
            self._cleanup_locked(now)
            job = self._jobs.get(job_id)
            if job is not None:
                job.updated_at = now
            return job

    def update(self, job_id: str, **fields: Any) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for name, value in fields.items():
                setattr(job, name, value)
            job.updated_at = time.time()
            return job

    def drop_session(self, session_id: str) -> int:
        """Cancel and remove every job belonging to a deleted session."""
        with self._lock:
            job_ids = [job_id for job_id, job in self._jobs.items() if job.session_id == session_id]
            for job_id in job_ids:
                self._jobs[job_id].cancel_flag.set()
                del self._jobs[job_id]
            return len(job_ids)

    def cleanup(self) -> int:
        with self._lock:
            return self._cleanup_locked(time.time())

    def _cleanup_locked(self, now: float) -> int:
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if now - job.updated_at > self.max_age_seconds
        ]
        for job_id in expired:
            self._jobs[job_id].cancel_flag.set()
            del self._jobs[job_id]
        return len(expired)


registry = JobRegistry()
executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="scansplitter-job")


def submit_job(
    kind: str,
    session_id: str,
    worker: Callable[[Callable[[int, str], None], Callable[[], bool]], dict[str, Any]],
) -> Job:
    """Create and submit a worker, translating its outcome into job state."""
    job = registry.create(kind, session_id)

    def run() -> None:
        if job.cancel_flag.is_set():
            registry.update(job.job_id, status="cancelled", stage="cancelled")
            return
        registry.update(job.job_id, status="running", stage="starting")

        def progress(percent: int, stage: str) -> None:
            if job.cancel_flag.is_set():
                raise JobCancelled
            registry.update(job.job_id, progress=max(0, min(99, int(percent))), stage=stage)

        try:
            result = worker(progress, job.cancel_flag.is_set)
            if job.cancel_flag.is_set():
                raise JobCancelled
            download_bytes = result.pop("__download_bytes", None)
            if download_bytes is not None:
                result["download_url"] = f"/api/jobs/{job.job_id}/download"
            registry.update(
                job.job_id,
                status="succeeded",
                progress=100,
                stage="complete",
                result=result,
                download_bytes=download_bytes,
            )
        except JobCancelled:
            registry.update(job.job_id, status="cancelled", stage="cancelled")
        except Exception as error:
            registry.update(job.job_id, status="failed", stage="failed", error=str(error))

    executor.submit(run)
    return job
