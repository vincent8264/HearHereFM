# Team API contracts

This is the current contract for the personal radio prototype. Coordinate any
further changes with the client, weather, Spotify, and TTS component owners.

## Flow

The client obtains the listener's location with permission. While the current
section is playing, it calls `POST /radio/next` with coordinates, a weather
description, the listener-local time, and the current section. The backend
returns the opposite mode: music -> narration, narration -> music. Calling
after a section ends is also supported, but adds generation latency.

GPT-6 Luna writes the next narration or names the next song. For narration,
the client sends the returned `text` to `POST /tts/jobs`, then polls the returned
`status_url` every 1–2 seconds. When `status` is `ready`, `audio_url` points to
the completed WAV. Keep music playing until the narration is prepared, then
pause music before playing the audio. Never overlap the two playback sections.
Request only one upcoming section; discard stale results if the location changes.
See [TTS integration](tts.md) for status, errors, queue limits, and storage.

## HTTP contract

`POST /radio/next` accepts:

```json
{
  "latitude": 37.7749,
  "longitude": -122.4194,
  "weather": "Sunny, 20 C",
  "time": "18:30",
  "current_state": "music"
}
```

Latitude must be between -90 and 90; longitude must be between -180 and 180.
`weather` is a nonempty description of at most 500 characters. `current_state`
is `music` or `narration` and means the section currently playing (or just ended).
`time` is
required and represents the listener's local clock time, typically in `HH:MM`
format; the backend does not infer it from coordinates. A success response
when requesting the section following music is:

```json
{"mode": "narration", "text": "The sunshine brings a gentle warmth to this stop..."}
```

When requesting the section following narration, the response is:

```json
{"mode": "music", "song_title": "Here Comes the Sun", "artist": "The Beatles"}
```

The narration text is ready for a separate TTS component. The song has not
been resolved to a Spotify track or checked for availability. Invalid input
returns HTTP 422. Missing `OPENAI_API_KEY` returns HTTP 503. Model or
model-output failure returns HTTP 502.

## Component boundaries and TODOs

| Component | Responsibility | Status |
| --- | --- | --- |
| Client | Obtain location; request the next section during playback; pre-generate narration; play sections separately | TODO |
| Weather | Supply a current weather description for coordinates | TODO |
| Decision | Alternate modes after each section | Implemented |
| LLM | Generate narration text or choose a song from location, weather, and local time | Implemented |
| Spotify | Resolve the chosen title and artist to a playable track, then control playback | TODO |
| TTS | Convert English narration to WAV with Kokoro; queue jobs and serve audio URLs | Implemented |
| Places | Supply verified local facts for richer narration | Future TODO |

Spotify track search is a future option for resolving model-chosen songs. Until
then, the music response is a suggestion, not a playable Spotify URI. The
radio endpoint does not store playback session state: callers send the current
section on each request. TTS job status is stored in memory and requires one
server worker. Spotify, weather provider, and richer place-fact contracts still
need team agreement.
