"""Verify the weather endpoint without external requests."""

from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

from app.main import app
from app.weather_api import service


def test_weather_route_fetches_current_conditions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.json.return_value = {
        "current": {
            "time": "2026-10-24T18:30",
            "temperature_2m": 68.0,
            "precipitation": 0.0,
            "rain": 0.0,
            "showers": 0.0,
        }
    }
    fetch = Mock(return_value=response)
    monkeypatch.setattr(service.requests, "get", fetch)
    with TestClient(app) as client:
        result = client.get("/weather", params={"latitude": 32.7, "longitude": -117.1})
    assert result.status_code == 200
    assert result.json() == {
        "time": "2026-10-24T18:30",
        "temperature_f": 68.0,
        "precipitation_in": 0.0,
        "rain_in": 0.0,
        "showers_in": 0.0,
    }
    response.raise_for_status.assert_called_once()
    fetch.assert_called_once_with(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": 32.7,
            "longitude": -117.1,
            "current": "temperature_2m,precipitation,rain,showers",
            "temperature_unit": "fahrenheit",
            "precipitation_unit": "inch",
            "timezone": "auto",
        },
        timeout=10,
    )


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"latitude": 91, "longitude": 0},
        {"latitude": 0, "longitude": -181},
        {"latitude": "invalid", "longitude": 0},
    ],
)
def test_weather_rejects_invalid_coordinates(
    monkeypatch: pytest.MonkeyPatch, params: dict
) -> None:
    fetch = Mock()
    monkeypatch.setattr(service.requests, "get", fetch)
    with TestClient(app) as client:
        assert client.get("/weather", params=params).status_code == 422
    fetch.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [requests.Timeout("provider details"), requests.HTTPError("provider details")],
)
def test_weather_provider_failure_is_502(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setattr(service.requests, "get", Mock(side_effect=error))
    with TestClient(app) as client:
        result = client.get("/weather", params={"latitude": 0, "longitude": 0})
    assert result.status_code == 502
    assert result.json() == {"detail": "Failed to retrieve weather."}


@pytest.mark.parametrize("payload", [{}, {"current": None}])
def test_weather_malformed_response_is_502(
    monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    response = Mock()
    response.json.return_value = payload
    monkeypatch.setattr(service.requests, "get", Mock(return_value=response))
    with TestClient(app) as client:
        result = client.get("/weather", params={"latitude": 0, "longitude": 0})
    assert result.status_code == 502


def test_weather_invalid_json_is_502(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    response.json.side_effect = ValueError("Invalid JSON")
    monkeypatch.setattr(service.requests, "get", Mock(return_value=response))
    with TestClient(app) as client:
        result = client.get("/weather", params={"latitude": 0, "longitude": 0})
    assert result.status_code == 502
