# Team API contracts

This is the current contract for the personal radio prototype. Coordinate any
further changes with the client, weather, Spotify, and TTS component owners.

## Flow

The client obtains the listener's location with permission. While the current
section is playing, it calls `POST /radio/next` with coordinates, a weather
description, the listener-local time, the current section, recent played history,
and optional listener input. The model selects music or narration for the next
section. The backend rejects repeated content and forces narration after three
consecutive songs. Calling after a section ends is also supported, but adds
generation latency.

Before generation, the backend looks for a named sight or museum through
Geoapify Places API v2 within 500 metres of the listener. If found, its name, type,
and approximate distance inform both narration and song selection. Provider
failure falls back to weather, time, and coordinates alone. GPT-6 Luna writes
the next narration or names the next song. For narration,
the client sends the returned `text` to `POST /tts/jobs`, then polls the returned
`status_url` every 1–2 seconds. When `status` is `ready`, `audio_url` points to
the completed WAV. Keep the current audio playing until the narration is prepared,
then pause or stop it before playing the WAV. Never overlap playback sections.
Request only one upcoming section; discard stale results if the location changes.
See [TTS integration](tts.md) for status, errors, queue limits, and storage.

### Optional user input

The headless program can capture spoken preferences such as "Play more lively
music" or "More detailed descriptions" and transcribe them to a string. Send it as
`user_input` on each relevant request; omit it when empty. The model uses it to
adjust song mood or narration detail, while the same factual and variety rules
still apply.

## HTTP contract

`POST /radio/next` accepts:

```json
{
  "latitude": 37.7749,
  "longitude": -122.4194,
  "weather": "Sunny, 20 C",
  "time": "18:30",
  "current_state": "music",
  "played_history": [
    {"mode": "music", "song_title": "Here Comes the Sun", "artist": "The Beatles", "spotify_uri": "spotify:track:6rqhFgbbKwnb9MLmUQDhG6"},
    {"mode": "narration", "text": "The afternoon light makes this a lovely place to pause."},
    {"mode": "music", "song_title": "Lovely Day", "artist": "Bill Withers"}
  ],
  "user_input": "Play more lively music and give more detailed descriptions"
}
```

Latitude must be between -90 and 90; longitude must be between -180 and 180.
`weather` is a nonempty description of at most 500 characters. `current_state`
is `idle`, `music`, or `narration`. Use `idle` before the first playback section;
otherwise send the section currently playing (or just ended).
`played_history` is optional, ordered oldest to newest, and contains up to ten
sections that actually started playback. Include the current section once it
starts. A music entry requires `song_title` and `artist` and may include its
resolved `spotify_uri`; a narration entry requires its exact script in `text`.
Send the most recent ten entries if the session is longer. `user_input` is
optional listener guidance of at most 2,000 characters, for example, "Play more
lively music" or "More detailed descriptions". Blank input is invalid; omit
the field if the listener has not provided guidance.

For headless voice input, use the string returned by `capture_text()` or the
`text` field from `POST /voice/transcribe` as `user_input`. Local recording is
capped at 60 seconds; STT and radio both accept up to 2,000 text characters.
Retain the listener's latest guidance for subsequent relevant requests; the
radio endpoint does not persist it. See [desktop voice setup](voice.md).

`time` is required and represents the listener's local clock time, typically in `HH:MM`
format; the backend does not infer it from coordinates. A success response
when the model chooses narration is:

```json
{"mode": "narration", "text": "The sunshine brings a gentle warmth to this stop..."}
```

When the model chooses music, the response is:

```json
{"mode": "music", "song_title": "Here Comes the Sun", "artist": "The Beatles"}
```

Either response is possible after either current state. The narration text is
ready for a separate TTS component. The music response
contains a suggestion, not a Spotify URI. The client sends it to
`POST /spotify/resolve`:

```json
{"song_title": "Here Comes the Sun", "artist": "The Beatles", "market": "US"}
```

The resolver searches Spotify with server-side app credentials and returns:

```json
{"spotify_uri": "spotify:track:6rqhFgbbKwnb9MLmUQDhG6"}
```

`market` is a required two-letter uppercase Spotify country code. It filters
search results to tracks available in that market. The resolver checks that
both title and artist match; a remastered or mixed version can match. A URI
does not start playback or guarantee the listener's account/device can play it.
If Spotify resolves to a URI already in recent history, the client should request
another candidate or skip it; the radio backend only sees the model's title and
artist when making its choice. No matching track returns 404, Spotify failure
returns 502, missing Spotify app credentials returns 503, and invalid input
returns 422. If no match is found, the client should request another song or
choose a fallback.

For `POST /radio/next`, invalid input returns HTTP 422. Missing
`OPENAI_API_KEY` returns HTTP 503. Model or model-output failure returns HTTP 502.

## Component boundaries and TODOs

| Component | Responsibility | Status |
| --- | --- | --- |
| Client | Obtain location; send played history and optional user input; request the next section during playback; pre-generate narration when selected; call Spotify resolver when selected; play sections separately | External to this repo |
| Weather | Fetch current conditions via `GET /weather`; client formats the description for radio | Implemented |
| Decision | Let the model select a mode; reject repeated content and runs longer than three songs | Implemented |
| LLM | Select a mode and generate narration or a song from context, history, and listener input | Implemented |
| Spotify resolver | Match the chosen title and artist to a market-filtered Spotify track URI | Implemented |
| Spotify playback | OAuth and Spotify Connect play/pause/state | Implemented; requires user authorization and a playback device |
| Desktop controller | Start from context or voice-triggered capture; retain history; prepare and play sections without a frontend | Implemented; see [desktop setup](desktop.md) |
| TTS | Convert English narration to WAV with Kokoro; queue jobs and serve audio URLs | Implemented |
| Places | Find a nearby named sight or museum with Geoapify; detailed verified facts are future work | Basic lookup implemented |

The place lookup requires `GEOAPIFY_API_KEY` in the server environment or a
local `.env` file. It requests up to 20 nearby results and chooses the nearest
named sight or museum. It is best effort and may add up to six seconds before
model generation. The client should credit both
[OpenStreetMap contributors](https://www.openstreetmap.org/copyright) and
[Geoapify](https://www.geoapify.com/) where users can see the source of place
names, as required for Geoapify's free plan.

The radio endpoint does not store playback session state: callers send the current
section and recent played history on each request. Generated or queued content
should enter history only when playback starts. Duplicate checks compare song
title and artist or near-identical narration text, then allow one model retry.
They cannot guarantee semantic novelty or detect alternate Spotify recordings.
TTS job status is stored in memory and requires one
server worker. Spotify playback and richer place-fact contracts still need
team agreement.

## Weather and location

`GET /weather?latitude=32.7157&longitude=-117.1611` returns current conditions
from Open-Meteo:

```json
{
  "time": "2026-10-24T18:30",
  "temperature_f": 68.0,
  "precipitation_in": 0.0,
  "rain_in": 0.0,
  "showers_in": 0.0
}
```

Coordinates are validated with the same ranges as the radio endpoint. Provider
failures or malformed responses return 502. The client can format a `weather`
description such as `68 F, no rain` and extract `18:30` from the returned local
`time` for `/radio/next`. The radio endpoint does not fetch weather automatically.

`GET /location` serves a minimal browser client that requests device location
permission on load. Its selector also offers four fixed demo locations that
do not require device permission:

| Preset | Representative point | Latitude | Longitude |
| --- | --- | ---: | ---: |
| Hollywood Boulevard | [Hollywood & Vine](https://commons.wikimedia.org/wiki/Category:Hollywood_and_Vine) | 34.10164 | -118.32667 |
| Cairo Egyptian Museum | [Museum at Tahrir Square](https://egypter.com/en/museums/egyptian-museum/) | 30.04785 | 31.23360 |
| Jeju | [Jeju City](https://ungegn.un.org/dashboard/cities/details?id=2614) | 33.509722 | 126.521944 |
| Rio de Janeiro | [City coordinates](https://ungegn.un.org/dashboard/cities/details?id=989) | -22.903 | -43.208 |

The page sends the selected coordinates to `/weather` and can request a radio
preview with that location, the weather description, and the weather provider's
local time. Changing the selection discards an outdated preview. The preview
uses `current_state="music"`
and empty history because it does not control playback. A playback client must
send its real state and history with the same location context. Browser location
may use GPS, Wi-Fi, or cellular positioning. Geolocation requires HTTPS except
for a browser using localhost on its own device; a phone connecting to a server
on the LAN therefore needs HTTPS. The client requests high accuracy and displays
the reported accuracy, but the browser does not guarantee use of GPS hardware.

The Python helper `app.location_api.get_location.get_my_location()` estimates
the backend server's location through ipapi.co, with ipwho.is as a fallback if the first provider fails. It is not exposed as an HTTP
route and is not used by the browser client or weather/radio endpoints. Neither
the IP helper nor the weather provider request sends an API key.
