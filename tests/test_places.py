"""Check nearby POI selection without making Geoapify requests."""

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from app.places import service


@pytest.fixture(autouse=True)
def configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEOAPIFY_API_KEY", "test-key")


def test_nearest_named_sight_or_museum_is_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.json.return_value = {
        "features": [
            {
                "properties": {"categories": ["entertainment.museum"]},
                "geometry": {"coordinates": [-117.1611, 32.716]},
            },
            {
                "properties": {
                    "name": "Nearby Museum",
                    "categories": ["entertainment.museum"],
                },
                "geometry": {"coordinates": [-117.1611, 32.7158]},
            },
            {
                "properties": {
                    "name": "Far Monument",
                    "categories": ["tourism.sights.memorial.monument"],
                },
                "geometry": {"coordinates": [-117.1611, 32.719]},
            },
            {
                "properties": {
                    "name": "Outside Search",
                    "categories": ["tourism.sights"],
                },
                "geometry": {"coordinates": [-117.1611, 33.0]},
            },
        ]
    }
    fetch = Mock(return_value=response)
    monkeypatch.setattr(service.requests, "post", fetch)

    place = service.find_nearby_place(32.7157, -117.1611)

    assert place == service.NearbyPlace("Nearby Museum", "museum", 11)
    fetch.assert_called_once_with(
        service.GEOAPIFY_URL,
        headers={"x-api-key": "test-key"},
        json={
            "categories": ["tourism.sights", "entertainment.museum"],
            "filter": {
                "type": "circle",
                "lon": -117.1611,
                "lat": 32.7157,
                "radius": 500,
            },
            "bias": {"type": "proximity", "lon": -117.1611, "lat": 32.7157},
            "limit": 20,
        },
        timeout=6,
    )


def test_sight_kind_and_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    response.json.return_value = {
        "features": [
            {
                "properties": {"name": "Monument", "categories": ["tourism.sights"]},
                "geometry": {"coordinates": [0, 0]},
            }
        ]
    }
    monkeypatch.setattr(service.requests, "post", Mock(return_value=response))
    assert service.find_nearby_place(0, 0) == service.NearbyPlace(
        "Monument", "sight", 0
    )

    response.json.return_value = {"features": []}
    assert service.find_nearby_place(0, 0) is None


@pytest.mark.parametrize("payload", [{}, {"features": "invalid"}])
def test_malformed_place_response_raises_lookup_error(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    response = Mock()
    response.json.return_value = payload
    monkeypatch.setattr(service.requests, "post", Mock(return_value=response))
    with pytest.raises(service.PlaceLookupError):
        service.find_nearby_place(0, 0)


def test_place_provider_failure_raises_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service.requests, "post", Mock(side_effect=requests.Timeout("timeout"))
    )
    with pytest.raises(service.PlaceLookupError):
        service.find_nearby_place(0, 0)


def test_missing_api_key_skips_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    monkeypatch.setattr(service, "ENV_FILE", tmp_path / "absent.env")
    fetch = Mock()
    monkeypatch.setattr(service.requests, "post", fetch)
    with pytest.raises(service.PlaceLookupError, match="GEOAPIFY_API_KEY"):
        service.find_nearby_place(0, 0)
    fetch.assert_not_called()
