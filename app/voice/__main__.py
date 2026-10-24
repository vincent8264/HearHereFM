"""Headless voice entry point: stdout or a UTF-8 file contains only recognized text."""

import argparse
import sys
from pathlib import Path
from uuid import uuid4

from app.voice.microphone import MicrophoneError, capture_text
from app.voice.transcription import (
    MAX_AUDIO_BYTES,
    STTUnavailableError,
    VoiceInputError,
    get_transcriber,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record speech and return only its text."
    )
    parser.add_argument(
        "--input", type=Path, help="Transcribe a file instead of the microphone."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Atomically save the UTF-8 string for a background consumer.",
    )
    parser.add_argument(
        "--device", type=int, help="Optional sounddevice input-device index."
    )
    args = parser.parse_args(argv)
    try:
        if args.input is not None:
            with args.input.open("rb") as recording:
                text = get_transcriber().transcribe(recording.read(MAX_AUDIO_BYTES + 1))
        else:
            text = capture_text(args.device)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_name(f".{args.output.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_text(text, encoding="utf-8")
                temporary.replace(args.output)
            finally:
                temporary.unlink(missing_ok=True)
        if sys.stdout is not None:
            print(text)
    except (VoiceInputError, STTUnavailableError, MicrophoneError, OSError) as exc:
        if sys.stderr is not None:
            print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
