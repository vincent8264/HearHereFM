"""Capture one utterance after an operating-system voice shortcut launches us."""

from collections import deque
from collections.abc import Iterable
from io import BytesIO

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from app.voice.transcription import VoiceInputError, get_transcriber

SAMPLE_RATE = 16000
BLOCK_SAMPLES = 1600


class MicrophoneError(RuntimeError):
    """No usable microphone or microphone permission is available."""


def collect_utterance(
    blocks: Iterable[NDArray[np.float32]],
    *,
    threshold: float = 0.015,
    wait_seconds: float = 10.0,
    silence_seconds: float = 1.2,
    max_seconds: float = 20.0,
) -> NDArray[np.float32]:
    """Wait for speech energy, retain its onset, and stop after trailing silence."""
    if threshold <= 0 or min(wait_seconds, silence_seconds, max_seconds) <= 0:
        raise ValueError("Recording limits and threshold must be positive.")
    pre_roll: deque[NDArray[np.float32]] = deque(maxlen=3)
    frames: list[NDArray[np.float32]] = []
    waited = captured = quiet = 0
    for block in blocks:
        samples = np.asarray(block, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            continue
        speaking = float(np.sqrt(np.mean(np.square(samples)))) >= threshold
        if not frames:
            pre_roll.append(samples.copy())
            waited += samples.size
            if speaking:
                frames.extend(pre_roll)
                captured = sum(len(frame) for frame in frames)
            elif waited >= wait_seconds * SAMPLE_RATE:
                raise VoiceInputError("No speech detected before microphone timeout.")
        else:
            frames.append(samples.copy())
            captured += samples.size
            quiet = 0 if speaking else quiet + samples.size
        if frames and (
            quiet >= silence_seconds * SAMPLE_RATE
            or captured >= max_seconds * SAMPLE_RATE
        ):
            return np.concatenate(frames)[: int(max_seconds * SAMPLE_RATE)]
    if not frames:
        raise VoiceInputError("No speech detected.")
    return np.concatenate(frames)[: int(max_seconds * SAMPLE_RATE)]


def record_utterance(device: int | None = None) -> bytes:
    """Open the microphone only for this request and return an in-memory WAV."""
    try:
        import sounddevice as sd

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SAMPLES,
            device=device,
        ) as stream:

            def blocks():
                while True:
                    block, overflowed = stream.read(BLOCK_SAMPLES)
                    if overflowed:
                        raise MicrophoneError(
                            "Microphone audio overflowed. Please retry."
                        )
                    yield block

            samples = collect_utterance(blocks())
    except (VoiceInputError, MicrophoneError):
        raise
    except Exception as exc:
        raise MicrophoneError(
            "Could not record audio. Check microphone access and input device."
        ) from exc
    output = BytesIO()
    sf.write(output, samples, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return output.getvalue()


def capture_text(device: int | None = None) -> str:
    """The teammate-facing contract: record one utterance and return a string."""
    return get_transcriber().transcribe(record_utterance(device))
