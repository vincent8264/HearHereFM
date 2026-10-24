"""Verify OAuth state, refresh, and playback routes with fake Spotify responses."""

from time import time
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.music import router as oauth


@pytest.fixture
def spotify(monkeypatch: pytest.MonkeyPatch):
    oauth.spotify_tokens.clear()
    oauth.oauth_pending.clear()
    monkeypatch.setattr(
        oauth,
        "_config",
        lambda name, default="": (
            "client-id" if name == "SPOTIFY_CLIENT_ID" else default
        ),
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        oauth.spotify_tokens.clear()
        oauth.oauth_pending.clear()


def test_spotify_login_uses_pkce_and_callback_state(
    spotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = spotify.get("/spotify/login", follow_redirects=False)
    assert response.status_code == 307
    params = parse_qs(urlparse(response.headers["location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert "user-modify-playback-state" in params["scope"][0]
    state = params["state"][0]
    verifier = oauth.oauth_pending[state][0]
    fake_response = Mock()
    fake_response.json.return_value = {
        "access_token": "private-access",
        "refresh_token": "private-refresh",
        "expires_in": 3600,
    }
    send = Mock(return_value=fake_response)
    monkeypatch.setattr(oauth.requests, "post", send)
    connected = spotify.get(
        "/spotify/callback", params={"code": "code", "state": state}
    )
    assert connected.status_code == 200
    assert connected.json() == {"status": "connected"}
    assert "private" not in connected.text
    assert send.call_args.kwargs["data"]["code_verifier"] == verifier
    assert (
        spotify.get(
            "/spotify/callback", params={"code": "code", "state": state}
        ).status_code
        == 400
    )


def test_bad_state_never_sends_token_request(
    spotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = Mock()
    monkeypatch.setattr(oauth.requests, "post", send)
    assert (
        spotify.get(
            "/spotify/callback", params={"code": "code", "state": "wrong"}
        ).status_code
        == 400
    )
    send.assert_not_called()


def test_expired_state_is_rejected(spotify) -> None:
    oauth.oauth_pending["expired"] = ("verifier", time() - 1)
    assert (
        spotify.get(
            "/spotify/callback", params={"code": "code", "state": "expired"}
        ).status_code
        == 400
    )


def test_refresh_keeps_refresh_token_private(
    spotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    oauth.spotify_tokens.update(
        {
            "access_token": "old-private",
            "refresh_token": "refresh-private",
            "expires_at": 0,
        }
    )
    response = Mock()
    response.json.return_value = {"access_token": "new-private", "expires_in": 3600}
    send = Mock(return_value=response)
    monkeypatch.setattr(oauth.requests, "post", send)
    player = oauth.get_player()
    assert player.access_token == "new-private"
    assert oauth.spotify_tokens["refresh_token"] == "refresh-private"
    assert send.call_args.kwargs["data"]["grant_type"] == "refresh_token"
    status = spotify.get("/spotify/status")
    assert status.json() == {"connected": True}
    assert "private" not in status.text


def test_pause_route_uses_connected_player(
    spotify, monkeypatch: pytest.MonkeyPatch
) -> None:
    player = Mock()
    player.pause.return_value = {"status": "paused"}
    monkeypatch.setattr(oauth, "get_player", lambda: player)
    assert spotify.post("/spotify/pause").json() == {"status": "paused"}
    player.pause.assert_called_once()


def test_missing_login_fails_without_exposing_tokens(spotify) -> None:
    response = spotify.post(
        "/spotify/play", json={"spotify_uri": "spotify:track:4iV5W9uYEdYUVa79Axb7Rh"}
    )
    assert response.status_code == 502
    assert "not connected" in response.json()["detail"]
