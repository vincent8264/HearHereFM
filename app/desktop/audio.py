"""Interruptible local WAV playback; never open a microphone here."""

from collections.abc import Callable
from pathlib import Path
from threading import Event

import soundfile as sf


class AudioPlaybackError(RuntimeError):
    """The local output device could not play the narration."""


def play_wav(
    path: Path, cancel: Event, on_started: Callable[[], None] | None = None
) -> bool:
    if cancel.is_set():
        return False
    try:
        import sounddevice as sd

        with (
            sf.SoundFile(path) as recording,
            sd.OutputStream(
                samplerate=recording.samplerate,
                channels=recording.channels,
                dtype="float32",
                blocksize=1024,
            ) as output,
        ):
            if cancel.is_set():
                return False
            started = False
            for block in recording.blocks(
                blocksize=1024, dtype="float32", always_2d=True
            ):
                if cancel.is_set():
                    output.abort()
                    return False
                output.write(block)
                if not started:
                    started = True
                    if on_started is not None:
                        on_started()
        return not cancel.is_set()
    except Exception as exc:
        raise AudioPlaybackError(
            "Could not play audio. Check the output device."
        ) from exc
