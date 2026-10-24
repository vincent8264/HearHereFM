# Hackathon starter

A small Python 3.12 and FastAPI repository for a team hackathon. It has a
health endpoint, tests, a smoke test, Ruff checks, and cross-platform CI.
`POST /radio/next` alternates music and narration based on the section that
currently playing (or just ended). GPT-6 Luna generates narration text or chooses
a song using the supplied location, weather, and local time. Spotify playback,
weather fetching, and local place facts remain integration work. See
[`docs/contracts.md`](docs/contracts.md) for the request and response shapes.

Local English TTS uses Kokoro on CPU. Submit `POST /tts/jobs` during music playback
to pre-generate the next narration and poll for a ready audio URL. `POST /tts`
also supports synchronous generation.
See [TTS setup and integration](docs/tts.md) to download the model and generate audio.

## Prerequisites and uv installation

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/).
uv downloads and manages Python 3.12 for this project, so a separate Python
installation is optional. Verify the install with `uv --version`.

macOS or Linux:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
```

Windows PowerShell (native Windows is supported; WSL is not required):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv --version
```

If `uv` is not recognized immediately, open a new terminal and try again.

## Initial setup

From the repository root on macOS or Linux:

```sh
git clone <repository-url>
cd <repository-directory>
uv python install 3.12
uv sync --locked
```

From the repository root on Windows PowerShell:

```powershell
git clone <repository-url>
Set-Location <repository-directory>
uv python install 3.12
uv sync --locked
```

Replace the angle-bracket placeholders with your team's Git URL and directory.
The same `uv` commands work in both shells. `uv sync --locked` creates a local
`.venv` and installs the versions recorded in `uv.lock`, including development
tools. The virtual environment is ignored by Git.

## Run and check the app

Start the server in one terminal:

```sh
uv run --locked uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/health> to see `{"status":"ok"}`. In another
terminal, run the live smoke test:

```sh
uv run --locked python scripts/smoke_test.py
```

For a different address, use
`uv run --locked python scripts/smoke_test.py --base-url http://127.0.0.1:9000`.
Stop the server with Ctrl+C. The interactive API docs are at
<http://127.0.0.1:8000/docs>.

Run automated tests and style checks from the repository root:

```sh
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

To apply formatting to code you changed, run `uv run --locked ruff format .`.

## Dependencies and environment variables

Coordinate dependency changes because `pyproject.toml` and `uv.lock` are shared:

```sh
uv add <runtime-package>
uv add --dev <development-package>
uv sync --locked
```

Commit changes to both dependency files in the same feature branch. Do not
commit `.venv`. The radio route requires `OPENAI_API_KEY` in the server process
environment or in a `.env` file at the repository root. A process environment
value takes precedence over `.env`. Copy `.env.example` to `.env` and replace
the placeholder with your key. Keep real keys local and never commit
credentials. Requests to the model use `gpt-6-luna`, and each call uses API
credits. Automated tests mock the model and do not use credits.

Example radio request while a music section is playing, to prepare narration:

```json
{
  "latitude": 37.7749,
  "longitude": -122.4194,
  "weather": "Sunny, 20 C",
  "time": "18:30",
  "current_state": "music"
}
```

Send this JSON to `POST /radio/next`, then send the returned `text` to
`POST /tts/jobs`. Set `current_state` to `narration` to prepare a song title and
artist for the following section. Calling after playback ends also works, but
requires waiting for generation. TTS and Spotify playback are separate stages;
the client pauses music before starting a ready narration.

## Team workflow and AI coding agents

Before dividing connected features, agree on their inputs and outputs in
[`docs/contracts.md`](docs/contracts.md). Pick file or component owners, create
a feature branch, and keep each change focused:

```sh
git switch main
git pull
git switch -c feature/<short-description>
# edit files, then run tests and Ruff checks
git add <files-you-changed>
git commit -m "Describe the change"
git push -u origin feature/<short-description>
```

Replace the placeholders with names that fit your team. Open a pull request
for review and let CI run on Linux, macOS, and Windows. Do not commit directly
to `main`. `AGENTS.md` is the shared instruction file for OpenAI Codex;
Claude Code imports it through `CLAUDE.md`. Agent changes follow the same
branch, ownership, testing, and review rules as human changes.

## Cross-platform troubleshooting

- Run commands from the repository root, where `pyproject.toml` and `uv.lock`
  live. The pytest configuration makes `app` importable there on all platforms.
- If `uv` cannot find Python 3.12, run `uv python install 3.12`, then retry
  `uv sync --locked`.
- If a locked command reports that the lockfile is outdated, coordinate a
  dependency update, run `uv lock`, and commit the updated `uv.lock` with
  `pyproject.toml`.
- If the smoke test cannot connect, leave the server running in its own
  terminal and check that its host and port match `--base-url`.
- If port 8000 is in use, start with
  `uv run --locked uvicorn app.main:app --reload --port 9000` and pass
  `--base-url http://127.0.0.1:9000` to the smoke test.
