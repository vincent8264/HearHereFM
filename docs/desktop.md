# Background personal radio

The headless controller now connects speech input, listener guidance, location,
weather, the LLM, Spotify resolution/playback, and local narration playback.
There is no product window. Siri or Windows Voice Access supplies the activation
trigger; our process does not continuously record or transcribe conversations.

## Spoken controls

Use these uncommon phrases as the **OS shortcut names**, without punctuation:

| Action | Mac Siri phrase | Windows Voice Access phrase |
| --- | --- | --- |
| Start without a request | Hey Siri, Radio start playback | Radio start playback |
| Start or update preferences | Hey Siri, Radio take my request | Radio take my request |
| Stop playback and capture | Hey Siri, Radio stop playback | Radio stop playback |

`Radio start playback` starts from location, weather, and time without playing
a listening prompt or opening the microphone. It clears previous listener
guidance while keeping playback history to avoid repeats.

After `Radio take my request`, wait for `Tell me what you would like to hear`, then say the
request, for example `Play upbeat music today with less talking`. Prompt playback
finishes before microphone capture begins. Capture waits at most 10 seconds for
speech, ends after 1.2 seconds of silence, and caps audio at 60 seconds. The
microphone closes afterward; ordinary conversation during playback is not sent
to STT or the LLM. To change preferences, invoke the activation phrase again.
The app's own prompts do not speak the activation phrases, reducing self-triggering.

Within the explicitly activated recording window, nearby speech can still be
picked up. This is not speaker identification. The native OS speech service has
its own listening behavior and permissions. Use headphones for the first demo
and verify Siri/Voice Access handoff on the actual machine.

## First setup

```sh
uv sync --locked
uv run --locked python scripts/download_tts_models.py
uv run --locked python scripts/download_stt_model.py
uv run --locked python -m app.desktop status
```

`status` starts a local daemon if necessary, but never opens the microphone.
The daemon binds only to `127.0.0.1:8000` and stays resident between commands.
It preserves the loaded models, latest guidance, and up to ten played sections
in memory. If another/older backend occupies port 8000, stop it first; the launcher
will not kill unrelated processes. Daemon logs live in ignored `data/desktop/`.

Required local `.env` values:

```dotenv
OPENAI_API_KEY=your-local-key
SPOTIFY_CLIENT_ID=your-local-client-id
# Optional:
SPOTIFY_MARKET=US
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/spotify/callback
# RADIO_LATITUDE=32.7157
# RADIO_LONGITUDE=-117.1611
# SPOTIFY_DEVICE_ID=your-web-player-device
```

If coordinates are omitted, desktop IP geolocation supplies an approximate
location, using ipapi.co with [ipwho.is](https://ipwhois.io/documentation) as a
backup when the first provider fails. Weather is refreshed every five minutes. Geoapify place context remains
optional, as in the radio API. Real keys and generated state remain ignored by Git.

For the Jeju City demo, use the existing Jeju preset coordinates in local `.env`:

```dotenv
RADIO_LATITUDE=33.509722
RADIO_LONGITUDE=126.521944
```

The desktop controller then skips IP geolocation and fetches weather/local time
for Jeju. Restart the daemon after changing demo coordinates to clear cached
location, weather, and history; reconnect Spotify afterward. `.env` stays local.

## Connect Spotify once per daemon lifetime

Register the exact redirect URI in the Spotify developer application. Open
[Spotify Web Player](https://open.spotify.com/) in your browser, sign in
with the account you will authorize, and manually play a song once to enable
browser audio. Keep that tab open, then run:

```sh
uv run --locked python -m app.desktop login
```

Spotify's browser pages provide account authorization and music playback.
The radio controller runs in the background. The callback keeps access/refresh
tokens in memory, refreshes expiring
tokens, and never returns them to the caller or LLM. Reconnect after daemon restart.
The desktop controller selects only devices named Web Player, including when
a preferred device ID is configured. Spotify Connect playback requires a
supported account/device and playback scopes;
see [Spotify's player API](https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback).
Desktop search and playback share the authorized user token through PKCE;
a client secret is not needed. The standalone `/spotify/resolve` endpoint uses
the connected user too, or app client credentials for catalog-only callers.

## macOS Siri setup

Create three Shortcuts with the exact names in the table. Each needs just a
**Run Shell Script** action:

Start without a request (`Radio start playback`):

```sh
/bin/sh /Users/skylining/compiled16/scripts/start_radio_macos.sh
```

Start/update a spoken request (`Radio take my request`):

```sh
/bin/sh /Users/skylining/compiled16/scripts/start_voice_macos.sh
```

Stop (`Radio stop playback`):

```sh
/bin/sh /Users/skylining/compiled16/scripts/stop_voice_macos.sh
```

Use the real checkout path on a different computer. Allow scripts in Shortcuts
settings, leave **Run as Administrator** unchecked, and grant microphone
permission when macOS requests it for the spoken-request shortcut. Do not add
another spoken prompt to the Shortcut: the controller already pauses Spotify,
plays its prompt, waits briefly, and only then opens the microphone.
The scripts launch/control the daemon and do not open a Terminal window.

Apple's documented mechanism:
[run a Shortcut with Siri](https://support.apple.com/en-gb/guide/shortcuts-mac/apd07c25bb38/mac).
Siri itself must be enabled and available; this does not wake a sleeping or locked
computer through a custom wake-word engine.

## Windows 11 Voice Access setup

Run once in PowerShell from the repository:

```powershell
.\scripts\create_voice_shortcut_windows.ps1
```

This creates `data\voice\Radio start playback.lnk`,
`data\voice\Radio take my request.lnk`, and
`data\voice\Radio stop playback.lnk`, using the virtual environment's `pythonw.exe`
so no console is shown. In Voice Access, create three custom voice shortcuts with
the table's phrases, each opening the matching `.lnk` file. Custom shortcuts are
documented for English variants. Follow
[Microsoft's setup](https://support.microsoft.com/en-gb/topic/use-voice-to-create-voice-access-shortcuts-3f03bdb9-a9ee-47a0-81d6-13c1c8ba2a08).
Windows device and OS handoff behavior must be verified on Windows; these tests
do not run a Windows VM or automatically change permissions/policies.

## Background sequencing

The first radio request uses `current_state: idle` and includes the latest speech
as `user_input`. The controller confirms Spotify's track URI/is-playing state
before adding music to history. Narration enters history when its output stream
starts. Only then is the next section prepared in a bounded worker, while the
current section is playing. History retains at most ten actually started sections.

At track end, Spotify is paused before local narration. Local WAV playback is
interruptible. The three-consecutive-songs rule is unchanged. If preparation takes
longer than the current section, there can be a gap rather than overlapping audio.
External Spotify pause/track changes stop the session instead of fighting the user.
If a selected song has no catalog match, the controller asks for one alternative
without changing the listener guidance. Other failures, or two unavailable song
selections, stop automated generation, retain an inspectable error, and attempt
one generic spoken notice. There is no unbounded provider retry loop.

Repeated start commands reuse the pending/default playback session, including
while it is preparing or already playing. A stop followed by start creates a new
session. Duplicate capture triggers during a pending capture reuse that capture;
a different request replaces the old operation after cancellation. These normal
repeats return 202. A closing controller returns 503 with Retry-After instead.

Activation updates invalidate pending content from the old request. Already-running
provider calls may finish, but their results cannot start playback. Stop cancels
capture/output and prevents subsequent sections from starting. Network calls
already in flight are bounded by their provider timeouts.

## CLI and local control

```sh
uv run --locked python -m app.desktop start
uv run --locked python -m app.desktop activate
uv run --locked python -m app.desktop stop
uv run --locked python -m app.desktop status
uv run --locked python -m app.desktop activate --input recorded-request.wav
uv run --locked python -m app.desktop shutdown
```

`start` begins contextual playback without microphone capture or previous
listener guidance. `activate --input` transcribes an existing recording rather than opening a mic.
`stop` stops the radio but keeps the daemon/models resident. `shutdown` gracefully
stops the managed daemon; use it before updating code or changing branches.

The local endpoints are `/desktop/activate`, `/desktop/start`, `/desktop/stop`,
`/desktop/status`, and `/desktop/shutdown`. They require loopback and
`X-Radio-Activation: explicit`; a normal browser request or external client cannot
arm capture. `/desktop/start` accepts no body (or `{}` / `{"user_input":null}`)
for contextual playback; `{"user_input":"..."}` still accepts already transcribed
guidance. Neither form opens a microphone. This is a single-user desktop controller,
not a multi-user hosted service.

## Validation limits

Automated tests simulate microphones, output devices, Spotify OAuth/player state,
provider failures, cancellation, and preparation races. They do not substitute for
testing Siri, the real microphone, local speaker output, and an authorized Spotify
playback device together. Raw speech input remains separately available via
`capture_text() -> str` and `POST /voice/transcribe`.
