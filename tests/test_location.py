"""Verify the IP lookup helper without making a network request."""

from unittest.mock import Mock

import pytest
import requests

from app.location_api import get_location


def test_ip_location_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    response.json.return_value = {
        "latitude": 32.7,
        "longitude": -117.1,
        "city": "San Diego",
    }
    fetch = Mock(return_value=response)
    monkeypatch.setattr(get_location.requests, "get", fetch)
    assert get_location.get_my_location() == {
        "latitude": 32.7,
        "longitude": -117.1,
        "city": "San Diego",
        "accuracy": "IP-based estimate",
    }
    fetch.assert_called_once_with("https://ipapi.co/json/", timeout=10)
    response.raise_for_status.assert_called_once()


def test_ip_location_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_location.requests, "get", Mock(side_effect=requests.Timeout("timeout"))
    )
    with pytest.raises(requests.Timeout):
        get_location.get_my_location()


@pytest.mark.parametrize(
    "failure", [requests.HTTPError("429"), ValueError("invalid JSON")]
)
def test_ip_location_uses_backup_on_primary_failure(monkeypatch, failure) -> None:
    response = Mock()
    response.json.return_value = {
        "success": True,
        "latitude": 32.7,
        "longitude": -117.1,
        "city": "San Diego",
    }
    fetch = Mock(side_effect=[failure, response])
    monkeypatch.setattr(get_location.requests, "get", fetch)
    assert get_location.get_my_location()["latitude"] == 32.7
    assert fetch.call_args.args == ("https://ipwho.is/",)


def test_ip_location_rejects_invalid_backup_coordinates(monkeypatch) -> None:
    primary, backup = Mock(), Mock()
    primary.json.return_value = {"error": True}
    backup.json.return_value = {"latitude": 999, "longitude": 0}
    monkeypatch.setattr(
        get_location.requests, "get", Mock(side_effect=[primary, backup])
    )
    with pytest.raises(ValueError, match="invalid coordinates"):
        get_location.get_my_location()
