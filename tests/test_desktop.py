"""Exercise the headless session without live microphone, output, or providers."""

from concurrent.futures import Future
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.desktop.controller import DesktopBusyError, RadioController
from app.desktop.services import PreparedSection
from app.main import app
from app.radio.schemas import MusicAction, NarrationAction


def eventually(check, timeout: float = 3) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if check():
            return
        sleep(0.01)
    pytest.fail("Background operation did not reach the expected state.")


class FakeServices:
    def __init__(self):
        self.events = []
        self.requests = []
        self.played = []
        self.prompt_gate = Event()
        self.prompt_gate.set()
        self.capture_gate = Event()
        self.capture_gate.set()
        self.finish_music = Event()
        self.finish_narration = Event()
        self.ensure_ready = Mock()
        self.error_notice = Mock()

    def pause(self):
        self.events.append("pause")

    def prompt(self, cancel):
        self.events.append("prompt")
        return self._wait(self.prompt_gate, cancel)

    def capture(self, cancel):
        self.events.append("capture")
        self._wait(self.capture_gate, cancel)
        return "Play upbeat music with less talking."

    def _wait(self, gate, cancel):
        while not cancel.is_set():
            if gate.wait(0.01):
                return True
        return False

    def context(self):
        return {
            "latitude": 32.7,
            "longitude": -117.1,
            "weather": "Sunny",
            "time": "18:30",
        }

    def prepare(self, request):
        self.requests.append(request)
        if len(self.requests) == 2:
            return PreparedSection(
                NarrationAction(text="A fresh seaside observation."),
                audio_path=Path("fake.wav"),
            )
        return PreparedSection(
            MusicAction(song_title=request.user_input[:50], artist="Artist"),
            uri="spotify:track:4iV5W9uYEdYUVa79Axb7Rh",
        )

    def start_music(self, section, cancel):
        self.played.append(section)
        return not cancel.is_set()

    def wait_music(self, section, cancel):
        self.events.append("music_wait")
        return self._wait(self.finish_music, cancel)

    def play_narration(self, section, cancel, on_started):
        self.pause()
        self.played.append(section)
        on_started()
        self.events.append("narration_started")
        return self._wait(self.finish_narration, cancel)


@pytest.fixture
def session():
    services = FakeServices()
    controller = RadioController(services)
    try:
        yield controller, services
    finally:
        controller.close()


def test_idle_and_status_never_record(session) -> None:
    controller, services = session
    assert controller.status()["phase"] == "idle"
    assert controller.status()["microphone_open"] is False
    assert services.events == []
    assert services.requests == []


def test_activation_waits_for_prompt_then_captures_exactly_once(session) -> None:
    controller, services = session
    services.prompt_gate.clear()
    services.capture_gate.clear()
    controller.activate()
    eventually(lambda: "prompt" in services.events)
    assert "capture" not in services.events
    assert controller.status()["microphone_open"] is False
    with pytest.raises(DesktopBusyError):
        controller.activate()
    services.prompt_gate.set()
    eventually(lambda: "capture" in services.events)
    assert controller.status()["microphone_open"] is True
    assert services.requests == []
    services.capture_gate.set()
    eventually(lambda: controller.status()["phase"] == "music")
    assert services.events.count("capture") == 1
    assert (
        services.events.index("pause")
        < services.events.index("prompt")
        < services.events.index("capture")
    )
    assert services.requests[0].current_state == "idle"
    assert services.requests[0].user_input == "Play upbeat music with less talking."
    assert controller.status()["microphone_open"] is False


def test_prepare_during_music_records_history_only_when_playback_starts(
    session,
) -> None:
    controller, services = session
    controller.activate("Play upbeat music.")
    eventually(lambda: len(services.requests) >= 2)
    status = controller.status()
    assert status["phase"] == "music"
    assert len(status["history"]) == 1
    assert status["history"][0]["mode"] == "music"
    assert len(services.requests[1].played_history) == 1
    assert services.requests[1].current_state == "music"
    services.finish_music.set()
    eventually(lambda: "narration_started" in services.events)
    assert [entry["mode"] for entry in controller.status()["history"]] == [
        "music",
        "narration",
    ]
    assert "capture" not in services.events


def test_stop_cancels_active_capture_without_a_model_call(session) -> None:
    controller, services = session
    services.capture_gate.clear()
    controller.activate()
    eventually(lambda: "capture" in services.events)
    controller.stop()
    eventually(lambda: controller.status()["phase"] == "idle")
    assert services.requests == []
    assert controller.status()["microphone_open"] is False


def test_new_input_discards_old_prepared_content(session) -> None:
    controller, services = session
    controller.activate("Old request.")
    eventually(lambda: len(services.requests) >= 2)
    controller.activate("New request.")
    eventually(lambda: len(services.played) >= 2)
    assert all(section.action.mode == "music" for section in services.played)
    assert services.played[-1].action.song_title == "New request."
    assert services.requests[-1].user_input == "New request."
    assert "capture" not in services.events


def test_stop_ignores_a_late_generation_result(session) -> None:
    controller, services = session
    started, release = Event(), Event()

    def prepare(request):
        started.set()
        assert release.wait(timeout=3)
        return PreparedSection(
            NarrationAction(text="Stale narration."), audio_path=Path("fake.wav")
        )

    services.prepare = prepare
    try:
        controller.activate("Start radio.")
        assert started.wait(timeout=1)
        controller.stop()
        eventually(lambda: controller.status()["phase"] == "idle")
    finally:
        release.set()
    controller.close()
    assert services.played == []
    assert controller.status()["history"] == []


def test_generation_timeout_is_terminal_instead_of_an_infinite_wait(session) -> None:
    controller, services = session
    services.prepare = Mock(side_effect=TimeoutError("provider timeout"))
    controller.activate("Start radio.")
    eventually(lambda: controller.status()["phase"] == "error")
    assert controller.status()["error"]
    eventually(lambda: services.error_notice.call_count == 1)
    assert services.played == []


def test_stop_pause_failure_is_reported_instead_of_claiming_idle(session) -> None:
    controller, services = session
    controller.activate("Start radio.")
    eventually(lambda: controller.status()["phase"] == "music")
    services.pause = Mock(side_effect=RuntimeError("Spotify unavailable"))
    controller.stop()
    eventually(lambda: controller.status()["phase"] == "error")
    assert "Could not confirm Spotify pause" in controller.status()["error"]


@pytest.mark.parametrize(
    "text", ["Cancel.", "Never mind", "Stop radio!", "取消", "停止播放"]
)
def test_explicit_cancel_utterance_does_not_reach_llm(session, text: str) -> None:
    controller, services = session
    controller.activate(text)
    eventually(lambda: controller.status()["phase"] == "idle")
    assert services.requests == []


def test_history_is_capped_at_ten_actually_started_sections(session) -> None:
    controller, services = session
    count = 0
    reached = Event()

    def prepare(request):
        nonlocal count
        count += 1
        return PreparedSection(
            NarrationAction(text=f"Script {count}"), audio_path=Path("fake.wav")
        )

    def play(section, cancel, on_started):
        on_started()
        if count >= 12:
            reached.set()
            cancel.wait(timeout=3)
            return False
        return True

    services.prepare, services.play_narration = prepare, play
    controller.activate("Tell me about this area.")
    assert reached.wait(timeout=2)
    history = controller.status()["history"]
    assert len(history) == 10
    assert history[-1]["text"] != "Script 1"
    controller.stop()


def test_completed_future_timeout_is_not_mistaken_for_pending_work(session) -> None:
    controller, _ = session
    future = Future()
    future.set_exception(TimeoutError("failed"))
    with pytest.raises(TimeoutError):
        controller._await(future, Event())


def test_desktop_control_requires_loopback_and_explicit_activation() -> None:
    with TestClient(app, client=("127.0.0.1", 10000)) as client:
        assert client.post("/desktop/activate").status_code == 403
        status = client.get(
            "/desktop/status", headers={"X-Radio-Activation": "explicit"}
        )
        assert status.status_code == 200
        assert status.json()["phase"] == "idle"
        assert status.json()["microphone_open"] is False
    with TestClient(app, client=("192.0.2.1", 10000)) as client:
        assert (
            client.post(
                "/desktop/activate", headers={"X-Radio-Activation": "explicit"}
            ).status_code
            == 403
        )


def test_programmatic_start_accepts_text_without_opening_mic() -> None:
    headers = {"X-Radio-Activation": "explicit"}
    with TestClient(app, client=("127.0.0.1", 10000)) as client:
        original = app.state.radio_controller
        fake = Mock(spec=RadioController)
        fake.activate.return_value = {"phase": "activation_pending"}
        app.state.radio_controller = fake
        try:
            response = client.post(
                "/desktop/start",
                json={"user_input": "Play upbeat music."},
                headers=headers,
            )
            assert response.status_code == 202
            fake.activate.assert_called_once_with("Play upbeat music.")
            assert (
                client.post(
                    "/desktop/start", json={"user_input": " "}, headers=headers
                ).status_code
                == 422
            )
        finally:
            app.state.radio_controller = original
