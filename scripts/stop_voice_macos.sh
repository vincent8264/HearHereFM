#!/bin/sh
# Call from a Siri Shortcut named Stop Radio. No microphone is opened.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
exec "$project_dir/.venv/bin/python" -m app.desktop stop >/dev/null
