# Team API contracts

This is the initial contract for the personal radio prototype. Review it with
component owners before building integrations that depend on it.

## Flow

The client obtains the listener's location with permission and calls
`POST /radio/next`. The backend will fetch weather and nearby place facts,
choose one mode, then return one action. Music and narration are separate
playback sections; their audio must not overlap.

## HTTP contract

`POST /radio/next` accepts JSON coordinates:

```json
{"latitude": 37.7749, "longitude": -122.4194}
```

Latitude must be between -90 and 90; longitude must be between -180 and 180.
The intended success response is one of:

```json
{"mode": "music", "spotify_uri": "spotify:track:example"}
```

```json
{"mode": "narration", "place_name": "Example Place", "audio_url": "https://example.com/narration"}
```

The route currently returns HTTP 501 for valid input until integrations are
implemented. Invalid input returns HTTP 422 through FastAPI validation.

## Component boundaries and TODOs

| Component | Responsibility | Status |
| --- | --- | --- |
| Client | Obtain location; present music or narration as separate sections | TODO |
| Weather | Fetch current conditions for coordinates | TODO |
| Places | Find nearby landmarks and factual source material | TODO |
| Decision | Choose one mode from weather, place facts, and user context | TODO |
| Spotify | Authenticate the listener, choose a track, and control playback | TODO |
| Narration | Generate a factual script and TTS audio | TODO |

External providers, credentials, error responses, session behavior, and
component owners are still to be agreed by the team.
