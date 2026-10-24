"""Download the multilingual base Whisper model for offline CPU inference."""

from pathlib import Path

from faster_whisper.utils import download_model


def main() -> None:
    directory = Path(__file__).resolve().parents[1] / "data" / "stt" / "base"
    print("Downloading multilingual Whisper base...", flush=True)
    download_model("base", output_dir=str(directory))
    print(f"Whisper model ready: {directory}")


if __name__ == "__main__":
    main()
