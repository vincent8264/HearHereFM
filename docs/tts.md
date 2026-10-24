# English narration TTS

The [desktop controller](desktop.md) uses this service directly to pre-generate
WAV files and plays them through the local output device, pausing Spotify first.
The HTTP job interface below remains available to other callers.

TTS accepts the narration text already written by the decision/narration component.
It does not select places, write scripts, play audio, or modify `/radio/next`.

## Setup

```sh
uv sync --locked
uv run --locked python scripts/download_tts_models.py
uv run --locked uvicorn app.main:app --reload --host 0.0.0.0
```

The initial download fetches the v1.0 Kokoro ONNX model and voices from
[kokoro-onnx's published release](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1).
No API key is needed. Inference runs locally on CPU after downloading the files.
The model is loaded on the first synthesis request and reused thereafter.
Default voice: `af_sarah`, American English, speed 1.0.

## Team integration contract

### Pre-generate the next narration (recommended)

1. While a section is playing, call `POST /radio/next` with the current state,
   recent played history, and context from [the radio contract](contracts.md).
   If the response mode is `narration`, send its `text` to `POST /tts/jobs` as
   `{"text": "..."}`. If it is `music`, resolve the song through Spotify instead.
2. The API returns HTTP 202 immediately with `job_id`, `status: "queued"`,
   `status_url`, `audio_url: null`, and `error: null`.
3. Poll `status_url` every 1–2 seconds. Status progresses through `queued`,
   `running`, then `ready` with a playable `audio_url`, or `failed` with `error`.
4. Keep the current section playing until narration is ready. At the intended
   transition, stop or pause the current audio, then play the prepared narration.
   Do not overlap audio. Add the narration to played history when it starts.

Only queue the next needed narration so it remains relevant to the listener's
location. The playback client owns timing and must ignore an outdated job if the
listener moves away. This module does not control Spotify or schedule playback.

The worker processes one job at a time. At most eight unfinished jobs are accepted;
further submissions return HTTP 429 with `Retry-After: 5`. The latest 128 status
records are retained; old finished records are evicted first. Unknown or evicted
IDs return 404. Records and pending jobs are lost on restart. Use **one server
worker**: the queue is in memory, not shared between processes or machines.
Shutdown waits for current synthesis and cancels queued work. Successful audio
files remain on disk even when a job record is evicted.

### Generate and wait

`POST /tts` with JSON:

```json
{"text": "Welcome to San Diego. Ahead of you is the waterfront."}
```

Successful response (HTTP 200):

```json
{"audio_url": "http://localhost:8000/tts/audio/0123456789abcdef0123456789abcdef.wav"}
```

The WAV is ready when the response arrives. Fetch it with `GET` at `audio_url`.
The radio endpoint returns `NarrationAction.text`; it has no `audio_url` field.
The client obtains the audio URL separately from TTS and uses it for playback.
Playback clients must stop or pause music before starting narration.
Text must be a nonblank string of at most 2,000 characters. Validation failures
return 422; missing/unloadable models return 503; synthesis/storage failures return
500. Requests are processed serially per process to avoid competing CPU inference.

For Python integration within the backend:

```python
from app.tts.service import get_tts_service

filename = get_tts_service().synthesize("Welcome to San Diego.")
# Build the public URL in the HTTP layer:
# str(request.url_for("tts_audio", filename=filename))
```

This is a blocking call: use a synchronous FastAPI route or run it in a worker
thread when called from async code. Keep one server worker for the hackathon so
only one model copy is loaded.

## Storage and hosting assumptions

Models and generated WAV files live in `data/tts/`, excluded from Git. Optionally
set the `TTS_DATA_DIR` environment variable to an absolute directory before running
both the download script and server. `.env` files are not automatically loaded.
Audio files persist until manually removed; there is no automatic retention policy.
Only publish non-sensitive demo narration: audio URLs have no authentication.

URLs use the incoming request's host and scheme. A phone must call the API using
the computer's reachable LAN address, rather than localhost. A reverse proxy must
forward the public host/scheme correctly. All workers must share the audio directory.

## Upstream licenses

- [Kokoro model weights](https://huggingface.co/hexgrad/Kokoro-82M): Apache-2.0.
- [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx): MIT.
- The English phonemizer uses eSpeak NG (GPL); preserve the applicable upstream
  notices and review transitive licenses when redistributing the runtime.

The model is open-weight; this project does not train it. No external paid TTS
service is called. Local compute and storage are still required.
