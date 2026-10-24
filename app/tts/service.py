"""Generate WAV files with a lazily loaded, CPU-based Kokoro model."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING
from uuid import uuid4

import soundfile as sf

if TYPE_CHECKING:
    from kokoro_onnx import Kokoro

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "tts"


def data_directory() -> Path:
    return Path(os.environ.get("TTS_DATA_DIR", str(DEFAULT_DATA_DIR))).resolve()


class TTSUnavailableError(RuntimeError):
    """The model files or local inference runtime are unavailable."""


class TTSSynthesisError(RuntimeError):
    """Speech generation or audio storage failed."""


class TTSService:
    """Serialize inference and reuse the loaded model between requests."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.audio_dir = data_dir / "audio"
        self._engine: Kokoro | None = None
        self._lock = Lock()

    def _load_engine(self) -> Kokoro:
        model = self.data_dir / "models" / "kokoro-v1.0.onnx"
        voices = self.data_dir / "models" / "voices-v1.0.bin"
        if not model.is_file() or not voices.is_file():
            raise TTSUnavailableError(
                "TTS model files are missing. Run uv run --locked python "
                "scripts/download_tts_models.py first."
            )
        try:
            from kokoro_onnx import Kokoro

            return Kokoro(str(model), str(voices))
        except Exception as exc:
            raise TTSUnavailableError("Could not load the TTS model.") from exc

    def synthesize(self, text: str) -> str:
        """Return the filename of a complete WAV using the af_sarah voice."""
        with self._lock:
            if self._engine is None:
                self._engine = self._load_engine()
            filename = f"{uuid4().hex}.wav"
            path = self.audio_dir / filename
            temporary = path.with_suffix(".tmp")
            try:
                samples, sample_rate = self._engine.create(
                    text, voice="af_sarah", speed=1.0, lang="en-us"
                )
                if len(samples) == 0 or sample_rate <= 0:
                    raise ValueError("The model returned empty audio.")
                self.audio_dir.mkdir(parents=True, exist_ok=True)
                sf.write(
                    temporary, samples, sample_rate, format="WAV", subtype="PCM_16"
                )
                temporary.replace(path)
            except Exception as exc:
                temporary.unlink(missing_ok=True)
                raise TTSSynthesisError("Could not generate speech.") from exc
            return filename


@lru_cache(maxsize=1)
def get_tts_service() -> TTSService:
    return TTSService(data_directory())
