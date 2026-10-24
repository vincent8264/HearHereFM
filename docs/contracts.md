# Team API contracts

This is the current contract for the personal radio prototype. Coordinate any
further changes with the client, weather, Spotify, and TTS component owners.

## Flow

The client obtains the listener's location with permission. When the current
section ends, it calls `POST /radio/next` with the coordinates, a weather
description, the listener-local time, and the section that just ended.
The backend alternates modes:
music ends -> narration, narration ends -> music. GPT-6 Luna writes the next
narration or names the next song. Music and narration are separate playback
sections; their audio must not overlap.

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
is `music` or `narration` and means the section that just ended. `time` is
required and represents the listener's local clock time, typically in `HH:MM`
format; the backend does not infer it from coordinates. A success response
after music is:

```json
{"mode": "narration", "text": "The sunshine brings a gentle warmth to this stop..."}
```

After narration, the response is:

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
| Client | Obtain location; send weather and ended section; play music and narration separately | TODO |
| Weather | Supply a current weather description for coordinates | TODO |
| Decision | Alternate modes after each section | Implemented |
| LLM | Generate narration text or choose a song from location, weather, and local time | Implemented |
| Spotify | Resolve the chosen title and artist to a playable track, then control playback | TODO |
| TTS | Convert narration text to speech audio | TODO |
| Places | Supply verified local facts for richer narration | Future TODO |

Spotify track search is a future option for resolving model-chosen songs. Until
then, the music response is a suggestion, not a playable Spotify URI. The
server does not store session state: callers send the current section on each
request. Spotify, TTS, weather provider, and richer place-fact contracts still
need team agreement.
