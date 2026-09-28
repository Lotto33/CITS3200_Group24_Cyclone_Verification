"""In-memory background jobs that relay dataset-pipeline stdout to API clients."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from io import TextIOBase
from threading import Lock, RLock, Thread
from uuid import uuid4


@dataclass
class UploadJob:
    job_id: str
    description: str
    status: str = "queued"
    messages: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None


_JOBS: dict[str, UploadJob] = {}
_JOBS_LOCK = RLock()
_STDOUT_LOCK = Lock()


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
    job = UploadJob(job_id=uuid4().hex, description=description)
    with _JOBS_LOCK:
        _JOBS[job.job_id] = job

    def run() -> None:
        with _JOBS_LOCK:
            job.status = "running"
            job.messages.append(f"Starting {description} processing.")
        writer = _JobLogWriter(job)
        try:
            # stdout is process-global, so pipeline jobs are serialized while captured.
            with _STDOUT_LOCK, redirect_stdout(writer):
                job.result = operation()
                writer.flush()
            with _JOBS_LOCK:
                job.status = "completed"
                job.messages.append("Processing complete.")
        except Exception as exc:
            writer.flush()
            with _JOBS_LOCK:
                job.status = "failed"
                job.error = str(exc)
                job.messages.append(f"ERROR: {exc}")

    Thread(target=run, name=f"dataset-upload-{job.job_id[:8]}", daemon=True).start()
    return job


def get_upload_job(job_id: str, since: int = 0) -> dict | None:
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
