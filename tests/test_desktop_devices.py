"""Device boundaries are simulated; these tests never capture or emit audio."""

from io import BytesIO
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest
import sounddevice as sd
import soundfile as sf

from app.desktop import audio
from app.desktop import services as integrations
from app.desktop.services import DesktopServices, PreparedSection
from app.music.spotify_playback import SpotifyPlaybackError
from app.radio.schemas import MusicAction, NarrationAction, RadioRequest
from app.voice.microphone import VoiceInputError, collect_utterance, record_utterance


def test_cancelled_recording_never_opens_microphone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancel = Event()
    cancel.set()
    opener = Mock()
    monkeypatch.setattr(sd, "InputStream", opener)
    with pytest.raises(VoiceInputError, match="cancelled"):
        record_utterance(cancel_event=cancel)
    opener.assert_not_called()


def test_recording_can_be_cancelled_between_blocks() -> None:
    cancel = Event()

    def blocks():
        yield np.full(1600, 0.1, dtype=np.float32)
        cancel.set()
        yield np.full(1600, 0.1, dtype=np.float32)

    with pytest.raises(VoiceInputError, match="cancelled"):
        collect_utterance(blocks(), cancel_event=cancel)


def test_recording_closes_stream_and_returns_wav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = MagicMock()
    stream.__enter__.return_value = stream
    stream.read.side_effect = [
        (np.full((1600, 1), 0.1, dtype=np.float32), False),
        *[(np.zeros((1600, 1), dtype=np.float32), False)] * 12,
    ]
    monkeypatch.setattr(sd, "InputStream", Mock(return_value=stream))
    wav = record_utterance()
    assert wav[:4] == b"RIFF"
    assert sf.info(BytesIO(wav)).samplerate == 16000
    stream.__exit__.assert_called_once()


def test_local_playback_started_callback_and_cancel_close_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "speech.wav"
    sf.write(path, np.zeros(4000, dtype=np.float32), 24000)
    stream = MagicMock()
    stream.__enter__.return_value = stream
    opener = Mock(return_value=stream)
    monkeypatch.setattr(sd, "OutputStream", opener)
    cancel = Event()
    started = Mock(side_effect=cancel.set)
    assert audio.play_wav(path, cancel, started) is False
    started.assert_called_once()
    stream.write.assert_called_once()
    stream.abort.assert_called_once()
    stream.__exit__.assert_called_once()


def test_cancelled_playback_never_opens_output(monkeypatch: pytest.MonkeyPatch) -> None:
    cancel = Event()
    cancel.set()
    opener = Mock()
    monkeypatch.setattr(sd, "OutputStream", opener)
    assert audio.play_wav(Path("unused.wav"), cancel) is False
    opener.assert_not_called()


def test_narration_pauses_spotify_before_local_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = DesktopServices()
    events = []
    services.pause = lambda: events.append("pause")
    monkeypatch.setattr(
        integrations, "play_wav", lambda *args: events.append("audio") or True
    )
    section = PreparedSection(
        NarrationAction(text="Hello."), audio_path=Path("fake.wav")
    )
    assert services.play_narration(section, Event(), lambda: None) is True
    assert events == ["pause", "audio"]


def test_spotify_confirmation_is_required_before_recording_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = DesktopServices()
    player = Mock()
    player.devices.return_value = {"devices": [{"id": "device", "is_active": True}]}
    player.state.return_value = {
        "track_uri": "spotify:track:4iV5W9uYEdYUVa79Axb7Rh",
        "is_playing": True,
    }
    monkeypatch.setattr(integrations, "get_player", lambda: player)
    section = PreparedSection(
        MusicAction(song_title="Song", artist="Artist"),
        uri="spotify:track:4iV5W9uYEdYUVa79Axb7Rh",
    )
    assert services.start_music(section, Event()) is True
    player.play_track.assert_called_once()
    player.state.assert_called_once()


def test_spotify_missing_device_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    services = DesktopServices()
    player = Mock()
    player.devices.return_value = {"devices": []}
    monkeypatch.setattr(integrations, "get_player", lambda: player)
    monkeypatch.setattr(integrations, "dotenv_values", lambda *args, **kwargs: {})
    monkeypatch.delenv("SPOTIFY_DEVICE_ID", raising=False)
    with pytest.raises(SpotifyPlaybackError, match="Open Spotify"):
        services.start_music(
            PreparedSection(
                MusicAction(song_title="Song", artist="Artist"),
                uri="spotify:track:4iV5W9uYEdYUVa79Axb7Rh",
            ),
            Event(),
        )
    player.play_track.assert_not_called()


def test_context_is_cached_and_uses_provider_local_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location = Mock(return_value={"latitude": 32.7, "longitude": -117.1})
    weather = Mock(
        return_value={
            "temperature_f": 68,
            "rain_in": 0,
            "precipitation_in": 0,
            "time": "2026-10-24T18:30",
        }
    )
    monkeypatch.setattr(integrations, "get_my_location", location)
    monkeypatch.setattr(integrations, "get_weather", weather)
    monkeypatch.setattr(integrations, "dotenv_values", lambda *args, **kwargs: {})
    monkeypatch.delenv("RADIO_LATITUDE", raising=False)
    monkeypatch.delenv("RADIO_LONGITUDE", raising=False)
    services = DesktopServices()
    first, second = services.context(), services.context()
    assert first == second
    assert first["time"] == "18:30"
    assert "68 F" in first["weather"]
    location.assert_called_once()
    weather.assert_called_once_with(32.7, -117.1)


def test_narration_preparation_produces_audio_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request = RadioRequest(
        latitude=32.7,
        longitude=-117.1,
        weather="Sunny",
        time="18:30",
        current_state="idle",
        user_input="Play something cheerful.",
    )
    tts = Mock(audio_dir=tmp_path)
    tts.synthesize.return_value = "narration.wav"
    monkeypatch.setattr(
        integrations, "next_action", lambda _: NarrationAction(text="Hello radio.")
    )
    monkeypatch.setattr(integrations, "get_tts_service", lambda: tts)
    prepared = DesktopServices().prepare(request)
    assert prepared.audio_path == tmp_path / "narration.wav"
    tts.synthesize.assert_called_once_with("Hello radio.")
