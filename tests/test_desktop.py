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
            MusicAction(
                song_title=(request.user_input or "Contextual song")[:50],
                artist="Artist",
            ),
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
    assert controller.activate()["phase"] == "prompting"
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
        assert client.post("/desktop/start").status_code == 403
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


def test_default_start_uses_context_without_prompt_or_microphone(session) -> None:
    controller, services = session
    controller.start()
    eventually(lambda: controller.status()["phase"] == "music")
    assert "prompt" not in services.events
    assert "capture" not in services.events
    assert controller.status()["microphone_open"] is False
    assert controller.status()["has_user_input"] is False
    request = services.requests[0]
    assert request.user_input is None
    assert request.current_state == "idle"
    assert request.latitude == 32.7
    assert request.weather == "Sunny"
    services.ensure_ready.assert_called_once()


def test_default_start_clears_old_guidance_and_discards_prefetched_content(
    session,
) -> None:
    controller, services = session
    controller.activate("Play loud rock music.")
    eventually(lambda: len(services.requests) >= 2)
    controller.start()
    eventually(lambda: len(services.played) >= 2)
    assert services.played[-1].action.song_title == "Contextual song"
    assert all(section.action.mode == "music" for section in services.played)
    assert services.requests[-1].user_input is None
    assert controller.status()["has_user_input"] is False
    assert "prompt" not in services.events
    assert "capture" not in services.events


@pytest.mark.parametrize("body", [None, {}, {"user_input": None}])
def test_start_endpoint_accepts_no_guidance_without_recording(body) -> None:
    headers = {"X-Radio-Activation": "explicit"}
    with TestClient(app, client=("127.0.0.1", 10000)) as client:
        original = app.state.radio_controller
        fake = Mock(spec=RadioController)
        fake.start.return_value = {
            "phase": "activation_pending",
            "microphone_open": False,
        }
        app.state.radio_controller = fake
        try:
            response = client.post("/desktop/start", json=body, headers=headers)
            assert response.status_code == 202
            assert response.json()["microphone_open"] is False
            fake.start.assert_called_once_with()
            fake.activate.assert_not_called()
        finally:
            app.state.radio_controller = original


def test_repeated_start_while_launch_pending_reuses_one_session(session) -> None:
    controller, services = session
    entered, release = Event(), Event()
    original_pause = services.pause

    def pause():
        original_pause()
        entered.set()
        release.wait(timeout=3)

    services.pause = pause
    try:
        controller.start()
        assert entered.wait(timeout=1)
        assert controller.start()["phase"] == "activation_pending"
        assert controller.start()["phase"] == "activation_pending"
        assert services.requests == []
    finally:
        release.set()
    eventually(lambda: controller.status()["phase"] == "music")
    assert len(services.played) == 1
    assert "prompt" not in services.events
    assert "capture" not in services.events


def test_repeated_start_while_preparing_does_not_cancel_generation(session) -> None:
    controller, services = session
    entered, release = Event(), Event()
    prepare = services.prepare

    def blocked_prepare(request):
        entered.set()
        release.wait(timeout=3)
        return prepare(request)

    services.prepare = blocked_prepare
    try:
        controller.start()
        assert entered.wait(timeout=1)
        eventually(lambda: controller.status()["phase"] == "preparing")
        assert controller.start()["phase"] == "preparing"
    finally:
        release.set()
    eventually(lambda: controller.status()["phase"] == "music")
    assert len(services.played) == 1
    assert controller.status()["error"] is None


def test_repeated_start_during_playback_leaves_current_track_playing(session) -> None:
    controller, services = session
    controller.start()
    eventually(lambda: len(services.requests) >= 2)
    events = list(services.events)
    history = controller.status()["history"]
    assert controller.start()["phase"] == "music"
    assert services.events == events
    assert controller.status()["history"] == history
    assert len(services.played) == 1


def test_start_can_replace_pending_voice_capture_without_409(session) -> None:
    controller, services = session
    services.capture_gate.clear()
    controller.activate()
    eventually(lambda: "capture" in services.events)
    controller.start()
    eventually(lambda: controller.status()["phase"] == "music")
    assert controller.status()["microphone_open"] is False
    assert services.requests[0].user_input is None
    assert services.events.count("capture") == 1
    assert len(services.played) == 1


def test_start_after_stop_is_a_new_session(session) -> None:
    controller, services = session
    controller.start()
    eventually(lambda: len(services.requests) >= 2)
    controller.stop()
    eventually(lambda: controller.status()["phase"] == "idle")
    controller.start()
    eventually(lambda: len(services.played) == 2)
    assert controller.status()["phase"] == "music"


def test_repeated_start_endpoint_accepts_pending_request(session) -> None:
    controller, services = session
    entered, release = Event(), Event()
    original_pause = services.pause

    def pause():
        original_pause()
        entered.set()
        release.wait(timeout=3)

    services.pause = pause
    headers = {"X-Radio-Activation": "explicit"}
    with TestClient(app, client=("127.0.0.1", 10000)) as client:
        original = app.state.radio_controller
        app.state.radio_controller = controller
        try:
            assert client.post("/desktop/start", headers=headers).status_code == 202
            assert entered.wait(timeout=1)
            response = client.post("/desktop/start", headers=headers)
            assert response.status_code == 202
            assert response.json()["phase"] == "activation_pending"
        finally:
            release.set()
            app.state.radio_controller = original


def test_shutdown_controller_reports_retryable_service_unavailable() -> None:
    headers = {"X-Radio-Activation": "explicit"}
    with TestClient(app, client=("127.0.0.1", 10000)) as client:
        original = app.state.radio_controller
        fake = Mock(spec=RadioController)
        fake.start.side_effect = DesktopBusyError("Radio is shutting down.")
        app.state.radio_controller = fake
        try:
            response = client.post("/desktop/start", headers=headers)
            assert response.status_code == 503
            assert response.headers["retry-after"] == "1"
        finally:
            app.state.radio_controller = original


def test_repeated_start_during_readiness_check_does_not_queue_restart(session) -> None:
    controller, services = session
    entered, release = Event(), Event()

    def readiness():
        entered.set()
        release.wait(timeout=3)

    services.ensure_ready.side_effect = readiness
    try:
        controller.start()
        assert entered.wait(timeout=1)
        assert controller.start()["phase"] == "activation_pending"
    finally:
        release.set()
    eventually(lambda: controller.status()["phase"] == "music")
    assert services.ensure_ready.call_count == 1
    assert len(services.played) == 1
