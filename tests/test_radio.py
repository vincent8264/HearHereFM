"""Tests for alternating radio sections and model integration."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.places.service import NearbyPlace, PlaceLookupError
from app.radio import llm, service


@pytest.fixture(autouse=True)
def no_live_places(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "find_nearby_place", lambda *_args: None)


@pytest.fixture
def model_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Capture Responses API calls without sending requests or using credits."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls: list[dict[str, object]] = []

    class FakeResponses:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            result_type = kwargs["text_format"]
            if result_type is llm.NarrationResult:
                result = llm.NarrationResult(
                    text="  A warm breeze follows the sunshine.  "
                )
            else:
                result = llm.SongResult(
                    song_title="  Here Comes the Sun  ", artist="  The Beatles  "
                )
            return SimpleNamespace(output_parsed=result)

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs == {"api_key": "test-key", "timeout": 20.0, "max_retries": 1}
            self.responses = FakeResponses()

    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    return calls


def test_music_ending_generates_narration(model_calls: list[dict[str, object]]) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 37.7749,
                "longitude": -122.4194,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": "music",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "mode": "narration",
        "text": "A warm breeze follows the sunshine.",
    }
    assert len(model_calls) == 1
    call = model_calls[0]
    assert call["model"] == "gpt-6-luna"
    assert call["text_format"] is llm.NarrationResult
    assert call["store"] is False
    assert json.loads(call["input"]) == {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "weather": "Sunny, 20 C",
        "time": "18:30",
    }


def test_narration_ending_generates_song(model_calls: list[dict[str, object]]) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 37.7749,
                "longitude": -122.4194,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": "narration",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "mode": "music",
        "song_title": "Here Comes the Sun",
        "artist": "The Beatles",
    }
    assert len(model_calls) == 1
    assert model_calls[0]["text_format"] is llm.SongResult
    assert json.loads(model_calls[0]["input"])["time"] == "18:30"


@pytest.mark.parametrize("current_state", ["music", "narration"])
def test_nearby_place_reaches_model_for_both_actions(
    model_calls: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    current_state: str,
) -> None:
    monkeypatch.setattr(
        service,
        "find_nearby_place",
        lambda *_args: NearbyPlace("Balboa Park", "attraction", 120),
    )
    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 32.7157,
                "longitude": -117.1611,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": current_state,
            },
        )
    assert response.status_code == 200
    assert json.loads(model_calls[0]["input"])["nearby_place"] == {
        "name": "Balboa Park",
        "kind": "attraction",
        "distance_m": 120,
    }
    assert "nearby_place" in model_calls[0]["instructions"]


def test_place_lookup_failure_keeps_radio_available(
    model_calls: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object) -> None:
        raise PlaceLookupError("Geoapify unavailable")

    monkeypatch.setattr(service, "find_nearby_place", fail)
    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 32.7157,
                "longitude": -117.1611,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": "music",
            },
        )
    assert response.status_code == 200
    assert "nearby_place" not in json.loads(model_calls[0]["input"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", 91),
        ("longitude", -181),
        ("weather", "  "),
        ("time", "25:61"),
        ("current_state", "paused"),
    ],
)
def test_radio_route_rejects_invalid_input(field: str, value: object) -> None:
    payload: dict[str, object] = {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "weather": "Sunny, 20 C",
        "time": "18:30",
        "current_state": "music",
    }
    payload[field] = value

    with TestClient(app) as client:
        response = client.post("/radio/next", json=payload)

    assert response.status_code == 422


def test_radio_route_requires_time() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 37.7749,
                "longitude": -122.4194,
                "weather": "Sunny, 20 C",
                "current_state": "music",
            },
        )

    assert response.status_code == 422


def test_dotenv_key_is_used_when_process_key_is_missing(
    model_calls: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setattr(llm, "ENV_FILE", env_file)

    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 37.7749,
                "longitude": -122.4194,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": "music",
            },
        )

    assert response.status_code == 200
    assert len(model_calls) == 1


def test_missing_api_key_reports_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "ENV_FILE", tmp_path / "absent.env")

    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 37.7749,
                "longitude": -122.4194,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": "music",
            },
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "OPENAI_API_KEY is not configured"}


def test_empty_model_result_reports_failure(
    model_calls: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        llm,
        "_generate",
        lambda *_args: llm.SongResult(song_title="  ", artist="The Beatles"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 37.7749,
                "longitude": -122.4194,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": "narration",
            },
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "The model returned an incomplete song choice"}
    assert model_calls == []


def test_model_api_failure_reports_bad_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FailingResponses:
        def parse(self, **_kwargs: object) -> None:
            raise llm.OpenAIError("simulated provider failure")

    class FailingOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            self.responses = FailingResponses()

    monkeypatch.setattr(llm, "OpenAI", FailingOpenAI)

    with TestClient(app) as client:
        response = client.post(
            "/radio/next",
            json={
                "latitude": 37.7749,
                "longitude": -122.4194,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": "music",
            },
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "Could not generate the next radio action"}
