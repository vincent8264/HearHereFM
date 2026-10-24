"""Download the published Kokoro ONNX model and voices before starting TTS."""

import os
from pathlib import Path
from urllib.request import urlopen

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "tts"
BASE_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
)


def main() -> None:
    directory = Path(os.environ.get("TTS_DATA_DIR", str(DEFAULT_DATA_DIR))) / "models"
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        target = directory / name
        if target.is_file():
            print(f"Already present: {target}")
            continue
        temporary = target.with_suffix(".download")
        print(f"Downloading {name}...", flush=True)
        try:
            with (
                urlopen(f"{BASE_URL}/{name}", timeout=120) as response,
                temporary.open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"Saved: {target}")


if __name__ == "__main__":
    main()
