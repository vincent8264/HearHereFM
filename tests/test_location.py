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
