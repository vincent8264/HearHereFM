"""Check a running server's health endpoint using the standard library."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the FastAPI health endpoint")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Server base URL (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()
    url = f"{args.base_url.rstrip('/')}/health"

    try:
        with urlopen(url, timeout=5) as response:
            status = response.status
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {url}: {exc}", file=sys.stderr)
        return 1

    if status != 200 or payload != {"status": "ok"}:
        print(
            f"FAIL: {url}: expected HTTP 200 and {{'status': 'ok'}}, "
            f"got HTTP {status} and {payload!r}",
            file=sys.stderr,
        )
        return 1

    print(f"PASS: {url}: HTTP 200, {{'status': 'ok'}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
