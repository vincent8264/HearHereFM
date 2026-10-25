"""Start a hidden local daemon on demand and send explicit voice activation."""

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import requests

from app.voice.transcription import MAX_AUDIO_BYTES, get_transcriber

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"X-Radio-Activation": "explicit"}


def server_status() -> dict | None:
    try:
        response = requests.get(
            f"{BASE_URL}/desktop/status", headers=HEADERS, timeout=2
        )
    except requests.ConnectionError:
        return None
    if response.status_code != 200:
        raise RuntimeError(
            "Port 8000 has an older/different server. Stop it before starting Radio."
        )
    data = response.json()
    if data.get("service") != "headless-radio-v1":
        raise RuntimeError("Port 8000 is not the desktop radio server.")
    return data


def ensure_server() -> None:
    if server_status() is not None:
        return
    directory = ROOT / "data" / "desktop"
    directory.mkdir(parents=True, exist_ok=True)
    options = (
        {
            "creationflags": subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP
        }
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with (directory / "server.log").open("ab") as log:
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "app.desktop.server",
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            **options,
        )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if server_status() is not None:
            return
        if child.poll() is not None:
            raise RuntimeError(
                "Radio server could not start. Check data/desktop/server.log."
            )
        time.sleep(0.2)
    raise RuntimeError("Radio server startup timed out. Check data/desktop/server.log.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Headless radio control; microphone is armed only by activate."
    )
    parser.add_argument(
        "command",
        choices=["start", "activate", "stop", "status", "login", "shutdown"],
        nargs="?",
        default="activate",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Use a recorded request instead of microphone capture.",
    )
    args = parser.parse_args(argv)
    try:
        if args.input is not None and args.command != "activate":
            raise ValueError("--input is only valid with activate.")
        if args.command == "shutdown" and server_status() is None:
            if sys.stdout is not None:
                print('{"status": "not_running"}')
            return 0
        ensure_server()
        if args.command == "login":
            webbrowser.open(f"{BASE_URL}/spotify/login")
            result = {"status": "Spotify authorization opened in your browser"}
        elif args.command == "status":
            result = server_status()
        else:
            endpoint = args.command
            payload = None
            if args.input is not None:
                with args.input.open("rb") as audio:
                    text = get_transcriber().transcribe(audio.read(MAX_AUDIO_BYTES + 1))
                endpoint, payload = "start", {"user_input": text}
            response = requests.post(
                f"{BASE_URL}/desktop/{endpoint}",
                headers=HEADERS,
                json=payload,
                timeout=10,
            )
            if response.status_code not in {200, 202}:
                raise RuntimeError(
                    f"Radio command failed with HTTP {response.status_code}."
                )
            result = response.json()
        if sys.stdout is not None:
            print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 -- The headless launcher must return a clean failure status.
        if sys.stderr is not None:
            print(
                str(exc)
                if isinstance(exc, (RuntimeError, ValueError))
                else "Radio command failed. Check the local server and model setup.",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
