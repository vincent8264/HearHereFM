# HearHereFM

HearHereFM is a location-aware personal radio prototype. It combines music from
Spotify with short spoken segments shaped by the listener's location, current
weather, local time, recent playback, and spoken preferences. A headless desktop
controller prepares the next segment while the current one plays, keeps a short
playback history, and stops when the listener asks it to.

The project is built with Python 3.12 and FastAPI. GPT-6 Luna chooses the next
song or writes narration; Kokoro generates local English speech; faster-whisper
transcribes a request after explicit activation. Open-Meteo provides weather,
and Geoapify can add a nearby named sight or museum when configured.

## What works today

- **Continuous radio session after activation:** the desktop controller selects,
  prepares, and plays successive music or narration segments. It starts only
  after a local command or configured OS voice shortcut. The microphone opens
  for one prompted request, then closes during playback.
- **Context:** desktop mode uses configured coordinates or an approximate
  location from the server's public IP. It fetches weather when preparing a
  segment and refreshes it after five minutes. Optional Geoapify lookup adds
  nearby place context.
- **Music and speech:** the controller resolves suggested songs through Spotify,
  plays them on a Spotify Web Player, and plays Kokoro-generated narration
  locally. It retains up to ten started segments and avoids repeats and long
  runs of songs.
- **Browser preview and API:** `/location` requests browser device location or
  offers four demo presets, shows weather, and can preview a radio decision.
  The preview does not start playback. The FastAPI routes also expose radio
  decisions, weather, Spotify resolution and control, transcription, and TTS.

This is a single-user local prototype. Desktop playback needs an authorized
Spotify account and an available Web Player. The browser preview is a separate
way to inspect context and a proposed next segment; it is not the desktop
playback controller. See [desktop setup](docs/desktop.md) and
[API contracts](docs/contracts.md) for details.

## Quick start: desktop radio

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run
these commands from the repository root. `uv` manages Python 3.12 and the
locked dependencies:

```sh
uv python install 3.12
uv sync --locked
uv run --locked python scripts/download_tts_models.py
uv run --locked python scripts/download_stt_model.py
```

Copy `.env.example` to `.env`. Set `OPENAI_API_KEY` and `SPOTIFY_CLIENT_ID` to
real values. Register `http://127.0.0.1:8000/spotify/callback` as the redirect
URI in your Spotify application. `GEOAPIFY_API_KEY` is optional. For a fixed
demo location, set both `RADIO_LATITUDE` and `RADIO_LONGITUDE`; otherwise the
desktop controller estimates the server's location from its public IP. Keep
`.env` and credentials out of Git. The desktop Spotify login uses PKCE and does
not require a client secret.

Open [Spotify Web Player](https://open.spotify.com/) in a browser and play a
song once so the browser is ready for audio. Then run:

```sh
uv run --locked python -m app.desktop status
uv run --locked python -m app.desktop login
uv run --locked python -m app.desktop activate
```

`status` starts the local daemon if needed but leaves the radio idle. `login`
opens Spotify authorization in your browser. `activate` plays a prompt, records
one spoken request, and starts the radio loop. For example, ask for upbeat music
with shorter narration. The daemon stays on `127.0.0.1:8000` between commands;
activating again updates the listener's preferences.

```sh
uv run --locked python -m app.desktop status
uv run --locked python -m app.desktop stop
uv run --locked python -m app.desktop shutdown
```

`stop` ends the session while leaving the daemon available. `shutdown` stops
the daemon. The [desktop guide](docs/desktop.md) covers Siri and Windows Voice
Access shortcuts, audio setup, and troubleshooting. Those OS shortcuts require
separate configuration; they are not installed by the commands above.

## Try the browser preview

Run the API server if the desktop daemon is not already using port 8000:

```sh
uv run --locked uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/location> on the same device. Allow device location
or choose a preset for Hollywood Boulevard, Cairo, Jeju, or Rio de Janeiro.
The page fetches current weather and can request a sample next radio segment.
Device location in a browser on another device needs HTTPS; the presets do not.
Interactive API docs are at <http://127.0.0.1:8000/docs>.

Do not run the development server and desktop daemon on port 8000 at the same
time. The browser preview can use the already running desktop daemon.

## How it fits together

1. Explicit activation captures a spoken request, or the local `/desktop/start`
   route receives already transcribed text.
2. The desktop controller gathers coordinates and weather, then uses the same
   decision logic as `POST /radio/next` for the next segment. The model may use
   optional nearby place context and the last ten played segments.
3. For music, the controller resolves a Spotify URI and confirms playback on a
   Web Player. For narration, it synthesizes a WAV and plays it locally.
4. Once a segment starts, the controller prepares the following one in a
   background worker. Stop or a new activation cancels the old session's
   subsequent playback.

The API can also be used independently: `GET /weather` accepts coordinates;
`POST /radio/next` accepts coordinates, weather, local time, current state, and
recent history; `POST /spotify/resolve` resolves a song suggestion; and
`POST /tts/jobs` queues narration audio. The standalone radio endpoint expects
the caller to supply weather and playback history. Request and response examples
are in [API contracts](docs/contracts.md).

## Development and validation

Run from the repository root:

```sh
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
node --test tests/test_device_location.mjs
```

The JavaScript test requires Node.js. The Python tests mock external providers
and audio devices. A full demo still depends on network access, local audio
devices, downloaded speech models, and a working Spotify authorization and
playback device. The [desktop guide](docs/desktop.md) describes those setup
requirements; [TTS](docs/tts.md) and [voice](docs/voice.md) have component
details.
