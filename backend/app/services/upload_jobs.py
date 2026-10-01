"""In-memory, single-process upload jobs.

Jobs are retained for a bounded TTL/count and disappear on process restart.
They are not suitable for multiple-worker deployments because each worker has
its own store. The current legacy pipeline uses ``redirect_stdout`` to relay
its existing print output; this is process-global and jobs are serialized, so
it should be replaced by explicit progress callbacks when the pipeline is
refactored. A timeout marks a job failed, although Python cannot safely kill a
running worker thread.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from io import TextIOBase
from threading import Lock, RLock, Thread, Timer
from time import monotonic
from uuid import uuid4


@dataclass
class UploadJob:
    job_id: str
    description: str
    created_monotonic: float = field(default_factory=monotonic)
    status: str = "queued"
    messages: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None


_JOBS: dict[str, UploadJob] = {}
_JOBS_LOCK = RLock()
_STDOUT_LOCK = Lock()
MAX_RETAINED_JOBS = 100
JOB_TTL_SECONDS = 60 * 60
JOB_TIMEOUT_SECONDS = 30 * 60


class _JobLogWriter(TextIOBase):
    def __init__(self, job: UploadJob) -> None:
        self.job = job
        self.buffer = ""
        self.console = __import__("sys").__stdout__

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if not text:
            return 0
        self.console.write(text)
        self.console.flush()
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._append(line.rstrip("\r"))
        return len(text)

    def flush(self) -> None:
        self.console.flush()
        if self.buffer:
            self._append(self.buffer.rstrip("\r"))
            self.buffer = ""

    def _append(self, line: str) -> None:
        with _JOBS_LOCK:
            self.job.messages.append(line)


def start_upload_job(description: str, operation: Callable[[], dict]) -> UploadJob:
    _prune_jobs()
    job = UploadJob(job_id=uuid4().hex, description=description)
    with _JOBS_LOCK:
        _JOBS[job.job_id] = job

    def run() -> None:
        with _JOBS_LOCK:
            job.status = "running"
            job.messages.append(f"Starting {description} processing.")

        def time_out() -> None:
            with _JOBS_LOCK:
                if job.status == "running":
                    job.status = "failed"
                    job.error = (
                        f"{description} exceeded the "
                        f"{JOB_TIMEOUT_SECONDS // 60}-minute timeout"
                    )
                    job.messages.append(f"ERROR: {job.error}")

        watchdog = Timer(JOB_TIMEOUT_SECONDS, time_out)
        watchdog.daemon = True
        watchdog.start()
        writer = _JobLogWriter(job)
        try:
            # stdout is process-global, so pipeline jobs are serialized while captured.
            with _STDOUT_LOCK, redirect_stdout(writer):
                job.result = operation()
                writer.flush()
            with _JOBS_LOCK:
                if job.status == "running":
                    job.status = "completed"
                    job.messages.append("Processing complete.")
        except Exception as exc:
            writer.flush()
            with _JOBS_LOCK:
                job.status = "failed"
                job.error = str(exc)
                job.messages.append(f"ERROR: {exc}")
        finally:
            watchdog.cancel()

    Thread(target=run, name=f"dataset-upload-{job.job_id[:8]}", daemon=True).start()
    return job


def _prune_jobs() -> None:
    now = monotonic()
    with _JOBS_LOCK:
        expired = [
            job_id
            for job_id, job in _JOBS.items()
            if job.created_monotonic + JOB_TTL_SECONDS < now
        ]
        for job_id in expired:
            _JOBS.pop(job_id, None)
        if len(_JOBS) > MAX_RETAINED_JOBS:
            oldest = sorted(
                _JOBS.values(), key=lambda job: job.created_monotonic
            )
            for job in oldest[: len(_JOBS) - MAX_RETAINED_JOBS]:
                _JOBS.pop(job.job_id, None)


def get_upload_job(job_id: str, since: int = 0) -> dict | None:
    _prune_jobs()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        return {
            "job_id": job.job_id,
            "description": job.description,
            "status": job.status,
            "messages": job.messages[since:],
            "next": len(job.messages),
            "error": job.error,
            "result": job.result,
        }
