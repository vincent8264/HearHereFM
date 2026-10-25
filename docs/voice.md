# Headless desktop speech input

For the complete background application, OS activation phrases, and Spotify
playback, follow [desktop radio setup](desktop.md). The raw string interfaces
below remain available independently.

Our component only records speech and returns the recognized **string**. It does
not interpret commands, call an LLM, change prompts, or control radio scheduling.
The LLM owner decides how to use a string such as `Play upbeat music today, with
less talking.` The separate desktop controller forwards it through `user_input`.

## Setup

```sh
uv sync --locked
uv run --locked python scripts/download_stt_model.py
```

Whisper base runs locally on CPU with language auto-detection. The model is stored
in ignored `data/stt/base/` and loaded on demand. This component needs no API key
and makes no LLM calls. The multilingual model supports English and Mandarin;
accuracy must be checked with the actual microphone and environment.
PyAV is constrained below 19 because faster-whisper 1.2.1 uses a removed argument
([upstream issue](https://github.com/SYSTRAN/faster-whisper/issues/1589)).

## String contract for the LLM owner

In the same Python process:

```python
from app.voice.microphone import capture_text

text: str = capture_text()
# Pass text to the teammate-owned LLM input handler here.
```

`capture_text()` records a single utterance. It waits at most 10 seconds for speech,
stops after about 1.2 seconds of trailing silence, and caps recording at 60 seconds.
Energy detection starts/stops recording; Whisper's VAD also filters silence. It is
not a semantic wake-word engine. Microphone/model failures raise exceptions and
do not produce an input string.

As a standalone process, stdout contains only the transcript on success:

```sh
uv run --locked python -m app.voice
uv run --locked python -m app.voice --input command.wav
uv run --locked python -m app.voice --output data/voice/latest.txt
```

The optional output file contains just the UTF-8 string and is replaced atomically
only on success. A background consumer should consume a **new file replacement**,
not repeatedly read a stale value. A failed capture leaves the previous file
unchanged; use process exit status or watch successful replacements. The integrated
desktop controller calls `capture_text()` directly and does not watch this file.
For a custom consumer, put the recognized string into
`user_input` in the existing `/radio/next` request alongside location, weather,
local time, current playback state, and recent played history. Both STT and
`user_input` accept up to 2,000 characters, so a valid transcript can be forwarded
without truncating it. Retain the latest input for subsequent requests as needed;
the radio endpoint does not remember preferences between calls.
`--device` accepts an optional sounddevice input-device index.
Recordings are processed in memory and not saved. Transcript files in `data/voice/`
are ignored by Git and remain local until removed.

For playback without recording a request, use `Radio start playback` and
`scripts/start_radio_macos.sh`; see [desktop setup](desktop.md).

## macOS: Siri launches a Shortcut

Apple documents that Siri can run a Shortcut by its name:
[run shortcuts with Siri](https://support.apple.com/en-gb/guide/shortcuts-mac/apd07c25bb38/mac).
The proposed flow is **Siri trigger -> launch -> speak request -> string**.

One-time setup on the demo Mac:

1. Create a Shortcut named `Radio take my request`.
2. Add **Run Shell Script**, using the absolute project path:

   ```sh
   /bin/sh /Users/skylining/compiled16/scripts/start_voice_macos.sh
   ```

3. If required, enable **Allow Running Scripts** in Shortcuts settings and grant
   microphone access when macOS requests it. See
   [Apple's scripting settings](https://support.apple.com/guide/shortcuts-mac/advanced-shortcuts-settings-apdfeb05586f/mac).
4. Test the Shortcut manually once, then invoke Siri and say `Radio take my request`.
   The script activates the background controller. Wait for its own spoken cue,
   then give the request. It sends the string into the existing radio input.

This is a concrete launch recipe, not a verified Siri/microphone installation.
Siri availability, microphone ownership during handoff, permissions, and timing
must be tested on the actual Mac. The process uses the project's Python directly;
Shortcuts does not need to find `uv` in its restricted PATH. The launcher exits;
the daemon stays resident with its microphone closed until the next activation.

## Windows 11: Voice Access launches a hidden Python process

Microsoft documents custom voice commands that open files or applications:
[Voice Access shortcuts](https://support.microsoft.com/en-gb/topic/use-voice-to-create-voice-access-shortcuts-3f03bdb9-a9ee-47a0-81d6-13c1c8ba2a08).
The custom-shortcut feature is documented for English language variants; use an
English trigger such as `Radio take my request`. This recipe targets Windows 11.

One-time setup on Windows:

1. Run the setup commands above, then in PowerShell run:

   ```powershell
   .\scripts\create_voice_shortcut_windows.ps1
   ```

2. The script creates ignored playback/request/stop `.lnk` files in `data\voice`, targeting
   `pythonw.exe -m app.desktop start`, `activate`, or `stop`. No console is shown.
   It does not install an autostart service or change system settings.
3. Enable Windows Voice Access. Create custom voice shortcuts named
   `Radio start playback`, `Radio take my request`, and `Radio stop playback`,
   opening the matching `.lnk`.
4. Say the trigger, allow a brief handoff, then speak the listening request.
   The controller transcribes it, supplies `user_input`, and manages playback.

Windows activation has not been executed on this Mac. Voice Access handoff,
microphone permissions, Python shortcut launching, and any local PowerShell
policy must be verified on the Windows machine. No system policies are changed
by this repository.

## Optional backend upload API

`POST /voice/transcribe`, multipart field `audio`, returns:

```json
{"text": "Play upbeat music today, with less talking."}
```

The field is forwarded verbatim as text; no intent or preference interpretation
is performed. Uploaded recordings may be WAV, MP3, M4A, or WebM if decodable.
Limit: 10 MiB and 60 seconds. Invalid/silent/overlong recordings return 422,
oversized uploads return 413, missing/unavailable models return 503.
The CLI does not require the API server to be running.

## Demo boundary

No product frontend is required. The OS speech service does the always-listening
activation, and our process records one subsequent request. This does not yet mean
a single continuous phrase such as `Hey Siri, Start Radio and play upbeat music`
is passed through intact: arbitrary Siri/Voice Access trailing speech is not
automatically forwarded. Use two separate utterances for the first demo.
The integrated controller now wires the LLM and playback pipeline as described
in [desktop radio setup](desktop.md).
