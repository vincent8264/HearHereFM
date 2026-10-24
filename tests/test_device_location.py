"""Verify the browser location client is reachable without an IP lookup."""

import pytest
from fastapi.testclient import TestClient

from app.location_api import get_location
from app.main import app


def test_device_location_client_is_served_without_ip_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> None:
        raise AssertionError("The server IP lookup must not locate the listener")

    monkeypatch.setattr(get_location, "get_my_location", fail)
    with TestClient(app) as client:
        page = client.get("/location")
        script = client.get("/location/client.mjs")

    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert 'src="/location/client.mjs"' in page.text
    for preset in (
        "hollywood_boulevard",
        "cairo_egyptian_museum",
        "jeju",
        "rio_de_janeiro",
    ):
        assert f'value="{preset}"' in page.text
    assert script.status_code == 200
    assert "text/javascript" in script.headers["content-type"]
