"""Verify transcription and headless string handoff without microphone access."""

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import av
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import app
from app.radio import llm
from app.radio import service as radio_service
from app.voice import __main__ as cli
from app.voice import microphone
from app.voice.transcription import (
    MAX_AUDIO_BYTES,
    STTUnavailableError,
    Transcriber,
    VoiceInputError,
    get_transcriber,
)


@pytest.fixture
def voice_client():
    transcriber = Mock(spec=Transcriber)
    transcriber.transcribe.return_value = "Play upbeat music with less talking."
    app.dependency_overrides[get_transcriber] = lambda: transcriber
    try:
        with TestClient(app) as client:
            yield client, transcriber
    finally:
        app.dependency_overrides.pop(get_transcriber, None)


def test_upload_returns_only_the_original_string(voice_client) -> None:
    client, transcriber = voice_client
    response = client.post(
        "/voice/transcribe",
        files={"audio": ("command.webm", b"recording", "audio/webm")},
    )
    assert response.status_code == 200
    assert response.json() == {"text": "Play upbeat music with less talking."}
    transcriber.transcribe.assert_called_once_with(b"recording")


@pytest.mark.parametrize("length", [501, 2000])
def test_long_voice_string_reaches_llm_without_truncation(
    voice_client, monkeypatch: pytest.MonkeyPatch, length: int
) -> None:
    client, transcriber = voice_client
    text = ("Please play upbeat music and keep narration short. " * 50)[
        : length - 1
    ] + "!"
    transcriber.transcribe.return_value = text
    fake_client = Mock()
    fake_client.responses.parse.return_value = SimpleNamespace(
        output_parsed=llm.RadioDecision(
            mode="music", text=None, song_title="Lovely Day", artist="Bill Withers"
        )
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "OpenAI", Mock(return_value=fake_client))
    monkeypatch.setattr(radio_service, "find_nearby_place", lambda *_args: None)
    transcript = client.post(
        "/voice/transcribe", files={"audio": ("command.wav", b"recording")}
    )
    assert transcript.status_code == 200
    response = client.post(
        "/radio/next",
        json={
            "latitude": 32.7,
            "longitude": -117.1,
            "weather": "Sunny",
            "time": "18:30",
            "current_state": "music",
            "played_history": [],
            "user_input": transcript.json()["text"],
        },
    )
    assert response.status_code == 200
    context = json.loads(fake_client.responses.parse.call_args.kwargs["input"])
    assert len(context["user_input"]) == length
    assert context["user_input"] == text


def test_oversized_upload_is_rejected_before_transcription(voice_client) -> None:
    client, transcriber = voice_client
    response = client.post(
        "/voice/transcribe",
        files={"audio": ("large.wav", b"x" * (MAX_AUDIO_BYTES + 1))},
    )
    assert response.status_code == 413
    transcriber.transcribe.assert_not_called()


@pytest.mark.parametrize(
    "error,status",
    [
        (VoiceInputError("No speech detected."), 422),
        (STTUnavailableError("Missing model."), 503),
    ],
)
def test_transcription_errors(voice_client, error: Exception, status: int) -> None:
    client, transcriber = voice_client
    transcriber.transcribe.side_effect = error
    response = client.post(
        "/voice/transcribe", files={"audio": ("command.wav", b"recording")}
    )
    assert response.status_code == status


def wav_bytes(seconds: float) -> bytes:
    output = BytesIO()
    sf.write(
        output, np.zeros(int(16000 * seconds), dtype=np.float32), 16000, format="WAV"
    )
    return output.getvalue()


def test_transcriber_decodes_audio_and_reuses_loaded_model() -> None:
    transcriber = Transcriber()
    model = Mock()
    model.transcribe.side_effect = [
        (iter([SimpleNamespace(text=" Play upbeat music. ")]), None),
        (iter([SimpleNamespace(text="今天只想聽歌。")]), None),
    ]
    transcriber._model = model
    assert transcriber.transcribe(wav_bytes(0.2)) == "Play upbeat music."
    assert transcriber.transcribe(wav_bytes(0.2)) == "今天只想聽歌。"
    assert model.transcribe.call_count == 2
    assert model.transcribe.call_args.args[0].shape == (3200,)
    assert model.transcribe.call_args.kwargs["vad_filter"] is True


@pytest.mark.parametrize("audio", [b"", b"not audio", wav_bytes(60.1)])
def test_transcriber_rejects_invalid_recordings(audio: bytes) -> None:
    transcriber = Transcriber()
    transcriber._model = Mock()
    with pytest.raises(VoiceInputError):
        transcriber.transcribe(audio)
    transcriber._model.transcribe.assert_not_called()


def test_silence_is_not_returned_as_a_command() -> None:
    transcriber = Transcriber()
    transcriber._model = Mock()
    transcriber._model.transcribe.return_value = (iter([]), None)
    with pytest.raises(VoiceInputError, match="No speech"):
        transcriber.transcribe(wav_bytes(0.2))


def test_webm_audio_decodes() -> None:
    output = BytesIO()
    with av.open(output, mode="w", format="webm") as container:
        stream = container.add_stream("libopus", rate=48000)
        frame = av.AudioFrame.from_ndarray(
            np.zeros((1, 9600), dtype=np.int16), format="s16", layout="mono"
        )
        frame.sample_rate = 48000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    transcriber = Transcriber()
    transcriber._model = Mock()
    transcriber._model.transcribe.return_value = (
        iter([SimpleNamespace(text="Hello radio.")]),
        None,
    )
    assert transcriber.transcribe(output.getvalue()) == "Hello radio."


def test_missing_model_never_downloads_implicitly(tmp_path: Path) -> None:
    with pytest.raises(STTUnavailableError, match="download_stt_model"):
        Transcriber(tmp_path)._load_model()


def block(volume: float) -> np.ndarray:
    return np.full(1600, volume, dtype=np.float32)


def test_capture_preserves_speech_onset_and_stops_after_silence() -> None:
    frames = [
        block(0),
        block(0),
        block(0.1),
        block(0.2),
        block(0),
        block(0),
        block(0.3),
    ]
    result = microphone.collect_utterance(frames, silence_seconds=0.2)
    assert len(result) == 6 * 1600
    assert result.max() == pytest.approx(0.2)
    assert np.all(result[:3200] == 0)
    assert np.allclose(result[3200:4800], 0.1)


def test_capture_times_out_if_nobody_speaks() -> None:
    with pytest.raises(VoiceInputError, match="timeout"):
        microphone.collect_utterance([block(0)] * 10, wait_seconds=0.5)


def test_capture_caps_continuous_sound() -> None:
    result = microphone.collect_utterance([block(0.1)] * 100, max_seconds=0.5)
    assert len(result) == 8000


def test_default_microphone_limit_allows_and_caps_one_minute() -> None:
    frames_read = 0

    def frames():
        nonlocal frames_read
        for _ in range(610):
            frames_read += 1
            yield block(0.1)

    result = microphone.collect_utterance(frames())
    assert len(result) == 60 * microphone.SAMPLE_RATE
    assert frames_read == 600


def test_one_minute_transcript_is_not_truncated_to_llm_character_limit() -> None:
    transcriber = Transcriber()
    transcriber._model = Mock()
    text = "Play upbeat songs and keep the narration brief. " * 15
    assert 500 < len(text.strip()) < 2000
    transcriber._model.transcribe.return_value = (
        iter([SimpleNamespace(text=text)]),
        None,
    )
    assert transcriber.transcribe(wav_bytes(60)) == text.strip()


def test_capture_string_contract_passes_recording_to_whisper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = Mock(return_value=b"wave")
    transcriber = Mock()
    transcriber.transcribe.return_value = "廣播少一點。"
    monkeypatch.setattr(microphone, "record_utterance", record)
    monkeypatch.setattr(microphone, "get_transcriber", lambda: transcriber)
    assert microphone.capture_text(device=2) == "廣播少一點。"
    record.assert_called_once_with(2, cancel_event=None)
    transcriber.transcribe.assert_called_once_with(b"wave")


def test_cli_outputs_only_the_string(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(cli, "capture_text", lambda device: "Play upbeat music.")
    assert cli.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Play upbeat music.\n"
    assert captured.err == ""


def test_cli_output_file_contains_utf8_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(cli, "capture_text", lambda device: "今天想聽輕快的歌。")
    target = tmp_path / "voice" / "latest.txt"
    assert cli.main(["--output", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == "今天想聽輕快的歌。"
    assert not list(target.parent.glob("*.tmp"))
    assert capsys.readouterr().out == "今天想聽輕快的歌。\n"


def test_cli_failure_never_publishes_a_new_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    target = tmp_path / "latest.txt"
    target.write_text("Previous command", encoding="utf-8")
    monkeypatch.setattr(
        cli, "capture_text", Mock(side_effect=VoiceInputError("No speech."))
    )
    assert cli.main(["--output", str(target)]) == 1
    assert target.read_text(encoding="utf-8") == "Previous command"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "No speech" in captured.err


def test_cli_file_input_never_opens_microphone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    recording = tmp_path / "command.wav"
    recording.write_bytes(b"wave")
    transcriber = Mock()
    transcriber.transcribe.return_value = "Only music today."
    capture = Mock()
    monkeypatch.setattr(cli, "capture_text", capture)
    monkeypatch.setattr(cli, "get_transcriber", lambda: transcriber)
    assert cli.main(["--input", str(recording)]) == 0
    capture.assert_not_called()
    assert capsys.readouterr().out == "Only music today.\n"
