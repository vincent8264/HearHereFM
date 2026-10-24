"""Tests for the radio route scaffold."""

from fastapi.testclient import TestClient

from app.main import app


def test_radio_route_reports_unconfigured_integrations() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/radio/next", json={"latitude": 37.7749, "longitude": -122.4194}
        )

    assert response.status_code == 501
    assert response.json() == {"detail": "Radio integrations are not configured yet"}


def test_radio_route_rejects_invalid_coordinates() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/radio/next", json={"latitude": 91, "longitude": -122.4194}
        )

    assert response.status_code == 422
