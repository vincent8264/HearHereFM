"""Return recognized speech as a string for the separately owned LLM."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.voice.transcription import (
    MAX_AUDIO_BYTES,
    STTUnavailableError,
    Transcriber,
    VoiceInputError,
    get_transcriber,
)

router = APIRouter(prefix="/voice", tags=["voice"])


class TranscriptResponse(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscriptResponse)
def transcribe(
    audio: Annotated[UploadFile, File()],
    transcriber: Annotated[Transcriber, Depends(get_transcriber)],
) -> TranscriptResponse:
    """Transcribe locally without interpreting intent or calling an LLM."""
    recording = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(recording) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio exceeds the 10 MiB limit.")
    try:
        text = transcriber.transcribe(recording)
        return TranscriptResponse(text=text)
    except VoiceInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except STTUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
