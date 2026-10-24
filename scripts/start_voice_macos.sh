#!/bin/sh
# Call with /bin/sh from a Siri Shortcut's Run Shell Script action.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
exec "$project_dir/.venv/bin/python" -m app.voice --output "$project_dir/data/voice/latest.txt"
