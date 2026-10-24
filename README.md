# Hackathon starter

The integrated background application is started with
`uv run --locked python -m app.desktop activate`. Configure the voice triggers and
Spotify authorization using [desktop radio setup](docs/desktop.md). Microphone
capture happens only after explicit activation and the spoken prompt.

A small Python 3.12 and FastAPI repository for a team hackathon. It has a
health endpoint, tests, a smoke test, Ruff checks, and cross-platform CI.
`POST /radio/next` uses GPT-6 Luna to choose music or narration and generate its
content from location, weather, local time, recent played history, and optional
listener input. The backend checks for repetition and limits consecutive songs.
`GET /weather`
fetches current conditions for supplied coordinates. The backend also looks up
nearby named sights and museums through Geoapify and resolves suggested songs to Spotify
track URIs through a separate endpoint. Spotify playback is handled by the client. See
[`docs/contracts.md`](docs/contracts.md) for the request and response shapes.

Local English TTS uses Kokoro on CPU. When radio selects narration, submit its
text to `POST /tts/jobs` during playback and poll for a ready audio URL. `POST /tts`
also supports synchronous generation.
See [TTS setup and integration](docs/tts.md) to download the model and generate audio.

Headless speech input is available with `uv run --locked python -m app.voice`.
It records one utterance and returns its text for the separately owned LLM.
`POST /voice/transcribe` also accepts uploaded recordings. See
[voice setup and desktop activation](docs/voice.md) for Siri and Windows Voice Access.

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

For `POST /spotify/resolve`, set `SPOTIFY_CLIENT_ID` and
`SPOTIFY_CLIENT_SECRET` in the server environment or `.env`. These are server-side
Spotify app credentials and must not be sent to the client. The resolver uses
Spotify client credentials to search its catalog; it does not control playback.

For nearby places in `POST /radio/next`, set `GEOAPIFY_API_KEY` in the server
environment or `.env`. The backend sends it in an `x-api-key` header. Missing
credentials or a provider failure leave the radio request working without a
nearby place.

Example radio request while a music section is playing:

```json
{
  "latitude": 37.7749,
  "longitude": -122.4194,
  "weather": "Sunny, 20 C",
  "time": "18:30",
  "current_state": "music",
  "played_history": [
    {"mode": "music", "song_title": "Lovely Day", "artist": "Bill Withers"}
  ],
  "user_input": "Play more lively music"
}
```

Send this JSON to `POST /radio/next`. If the response mode is `narration`, send
its `text` to `POST /tts/jobs`. If it is `music`, send its title and artist to
`POST /spotify/resolve` with a two-letter market, such as `US`, to obtain a
`spotify_uri` for playback. Add each section to `played_history` once playback
starts; send at most the latest ten in oldest-to-newest order. `user_input` is
optional and can be omitted. Calling after playback ends also works, but
requires waiting for generation. TTS and Spotify playback are separate stages;
the client pauses current audio before starting a ready narration.

For both radio modes, the backend searches within 500 metres for a named
Geoapify sight or museum. If one is nearby, the model receives its name, type, and approximate
distance. If the lookup fails or finds nothing, the radio request continues
without place context. The model is instructed not to invent facts about a place.

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
