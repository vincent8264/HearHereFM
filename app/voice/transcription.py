"""Transcribe short recordings locally with multilingual Whisper."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "stt" / "base"
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 60
RADIO_VOCABULARY = (
    "Personal radio commands: start radio, stop radio, upbeat music, relaxing "
    "songs, less talking, music only. 開始播放、輕快音樂、少一點廣播、只聽音樂。"
)


class VoiceInputError(ValueError):
    """Audio cannot be decoded or does not contain usable speech."""


class STTUnavailableError(RuntimeError):
    """The speech model cannot be loaded or run."""


class Transcriber:
    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        self.model_dir = model_dir
        self._model: WhisperModel | None = None
        self._lock = Lock()

    def _load_model(self) -> WhisperModel:
        if not (self.model_dir / "model.bin").is_file():
            raise STTUnavailableError(
                "Whisper model is missing. Run uv run --locked python "
                "scripts/download_stt_model.py first."
            )
        try:
            from faster_whisper import WhisperModel

            return WhisperModel(
                str(self.model_dir),
                device="cpu",
                compute_type="int8",
                local_files_only=True,
                cpu_threads=4,
            )
        except Exception as exc:
            raise STTUnavailableError("Could not load the speech model.") from exc

    def transcribe(self, audio: bytes) -> str:
        if not audio:
            raise VoiceInputError("Audio is empty.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise VoiceInputError("Audio exceeds the 10 MiB limit.")
        try:
            from faster_whisper.audio import decode_audio

            samples = decode_audio(BytesIO(audio), sampling_rate=16000)
        except Exception as exc:
            raise VoiceInputError("Could not decode this audio recording.") from exc
        if not len(samples) or len(samples) > MAX_AUDIO_SECONDS * 16000:
            raise VoiceInputError("Audio must be between 0 and 60 seconds long.")
        with self._lock:
            if self._model is None:
                self._model = self._load_model()
            try:
                segments, _ = self._model.transcribe(
                    samples,
                    beam_size=5,
                    vad_filter=True,
                    condition_on_previous_text=False,
                    initial_prompt=RADIO_VOCABULARY,
                )
                text = " ".join(segment.text.strip() for segment in segments).strip()
            except Exception as exc:
                raise STTUnavailableError("Speech recognition failed.") from exc
        if not text:
            raise VoiceInputError("No speech detected. Please try again.")
        if len(text) > 2000:
            raise VoiceInputError("The spoken command is too long.")
        return text


@lru_cache(maxsize=1)
def get_transcriber() -> Transcriber:
    return Transcriber()
