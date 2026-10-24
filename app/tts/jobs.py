"""Small, bounded in-process queue for pre-generating narration."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import Request

from app.tts.service import TTSSynthesisError, TTSUnavailableError

logger = logging.getLogger(__name__)


class QueueFullError(RuntimeError):
    """The local synthesis queue is at capacity."""


@dataclass(frozen=True)
class SpeechJob:
    job_id: str
    status: Literal["queued", "running", "ready", "failed"] = "queued"
    filename: str | None = None
    error: str | None = None


class SpeechJobs:
    """One inference worker; retain bounded status records until restart."""

    def __init__(self, max_pending: int = 8, max_records: int = 128) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")
        self._lock = Lock()
        self._jobs: dict[str, SpeechJob] = {}
        self._max_pending = max_pending
        self._max_records = max_records

    def submit(self, text: str, synthesize: Callable[[str], str]) -> SpeechJob:
        with self._lock:
            pending = sum(
                job.status in {"queued", "running"} for job in self._jobs.values()
            )
            if pending >= self._max_pending:
                raise QueueFullError("TTS queue is full. Try again later.")
            if len(self._jobs) >= self._max_records:
                oldest_finished = next(
                    (
                        key
                        for key, job in self._jobs.items()
                        if job.status in {"ready", "failed"}
                    ),
                    None,
                )
                if oldest_finished is None:
                    raise QueueFullError("TTS queue is full. Try again later.")
                del self._jobs[oldest_finished]
            job = SpeechJob(job_id=uuid4().hex)
            self._jobs[job.job_id] = job
            try:
                self._executor.submit(self._run, job.job_id, text, synthesize)
            except RuntimeError:
                del self._jobs[job.job_id]
                raise QueueFullError("TTS worker is shutting down.") from None
            return job

    def get(self, job_id: str) -> SpeechJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _update(self, job: SpeechJob) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def _run(self, job_id: str, text: str, synthesize: Callable[[str], str]) -> None:
        job = SpeechJob(job_id=job_id, status="running")
        self._update(job)
        try:
            filename = synthesize(text)
        except (TTSUnavailableError, TTSSynthesisError) as exc:
            self._update(replace(job, status="failed", error=str(exc)))
        except Exception:  # noqa: BLE001 -- Worker failures must leave a terminal status.
            logger.error("Unexpected failure in TTS job %s", job_id)
            self._update(
                replace(job, status="failed", error="Could not generate speech.")
            )
        else:
            self._update(replace(job, status="ready", filename=filename))

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


def get_speech_jobs(request: Request) -> SpeechJobs:
    return request.app.state.speech_jobs
