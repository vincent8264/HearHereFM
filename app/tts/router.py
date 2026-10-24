"""HTTP interface for speech synthesis and generated audio."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.tts.jobs import QueueFullError, SpeechJob, SpeechJobs, get_speech_jobs
from app.tts.service import (
    TTSService,
    TTSSynthesisError,
    TTSUnavailableError,
    get_tts_service,
)

router = APIRouter(prefix="/tts", tags=["tts"])
Service = Annotated[TTSService, Depends(get_tts_service)]
Jobs = Annotated[SpeechJobs, Depends(get_speech_jobs)]


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must contain non-whitespace characters.")
        return value.strip()


class SpeechResponse(BaseModel):
    audio_url: str


class SpeechJobResponse(BaseModel):
    job_id: str
    status: str
    status_url: str
    audio_url: str | None = None
    error: str | None = None


def job_response(request: Request, job: SpeechJob) -> SpeechJobResponse:
    return SpeechJobResponse(
        job_id=job.job_id,
        status=job.status,
        status_url=str(request.url_for("tts_job_status", job_id=job.job_id)),
        audio_url=(
            str(request.url_for("tts_audio", filename=job.filename))
            if job.filename is not None
            else None
        ),
        error=job.error,
    )


@router.post("/jobs", response_model=SpeechJobResponse, status_code=202)
def submit_job(
    request: Request, body: SpeechRequest, service: Service, jobs: Jobs
) -> SpeechJobResponse:
    """Queue the next narration while music is playing."""
    try:
        job = jobs.submit(body.text, service.synthesize)
    except QueueFullError as exc:
        raise HTTPException(
            status_code=429, detail=str(exc), headers={"Retry-After": "5"}
        ) from exc
    return job_response(request, job)


@router.get("/jobs/{job_id}", response_model=SpeechJobResponse, name="tts_job_status")
def job_status(request: Request, job_id: str, jobs: Jobs) -> SpeechJobResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="TTS job not found.")
    return job_response(request, job)


@router.post("", response_model=SpeechResponse)
def synthesize(
    request: Request, body: SpeechRequest, service: Service
) -> SpeechResponse:
    """Generate English narration; return a URL after the WAV is ready."""
    try:
        filename = service.synthesize(body.text)
    except TTSUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TTSSynthesisError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SpeechResponse(
        audio_url=str(request.url_for("tts_audio", filename=filename))
    )


@router.get("/audio/{filename}", name="tts_audio")
def audio(filename: str, service: Service) -> FileResponse:
    """Serve generated WAV files without exposing arbitrary filesystem paths."""
    if re.fullmatch(r"[0-9a-f]{32}\.wav", filename) is None:
        raise HTTPException(status_code=404, detail="Audio not found.")
    path = service.audio_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found.")
    return FileResponse(path, media_type="audio/wav")
