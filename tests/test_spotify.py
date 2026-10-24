"""Test Spotify URI resolution without sending catalog requests."""

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

from app.main import app
from app.radio import llm
from app.radio import service as radio_service
from app.spotify import service

URI = "spotify:track:6rqhFgbbKwnb9MLmUQDhG6"


@pytest.fixture
def spotify_responses(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test-secret")
    token = Mock()
    token.json.return_value = {"access_token": "test-token"}
    search = Mock()
    search.json.return_value = {
        "tracks": {
            "items": [
                {
                    "name": "Here Comes the Sun - Remastered 2009",
                    "artists": [{"name": "The Beatles"}],
                    "uri": URI,
                }
            ]
        }
    }
    post = Mock(return_value=token)
    get = Mock(return_value=search)
    monkeypatch.setattr(service.requests, "post", post)
    monkeypatch.setattr(service.requests, "get", get)
    return post, get


def test_resolve_song_returns_spotify_uri(spotify_responses: tuple[Mock, Mock]) -> None:
    post, get = spotify_responses
    with TestClient(app) as client:
        response = client.post(
            "/spotify/resolve",
            json={
                "song_title": "Here Comes the Sun",
                "artist": "The Beatles",
                "market": "US",
            },
        )
    assert response.status_code == 200
    assert response.json() == {"spotify_uri": URI}
    post.assert_called_once_with(
        service.TOKEN_URL,
        auth=("test-id", "test-secret"),
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    assert get.call_args.kwargs["params"] == {
        "q": 'track:"Here Comes the Sun" artist:"The Beatles"',
        "type": "track",
        "limit": 10,
        "market": "US",
    }


def test_radio_song_can_be_resolved_for_playback(
    spotify_responses: tuple[Mock, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(radio_service, "find_nearby_place", lambda *_args: None)
    monkeypatch.setattr(
        llm,
        "_generate",
        lambda *_args, **_kwargs: llm.RadioDecision(
            mode="music",
            text=None,
            song_title="Here Comes the Sun",
            artist="The Beatles",
        ),
    )
    with TestClient(app) as client:
        radio = client.post(
            "/radio/next",
            json={
                "latitude": 32.7157,
                "longitude": -117.1611,
                "weather": "Sunny, 20 C",
                "time": "18:30",
                "current_state": "narration",
            },
        )
        assert radio.status_code == 200
        song = radio.json()
        assert song.pop("mode") == "music"
        resolved = client.post("/spotify/resolve", json={**song, "market": "US"})
    assert resolved.status_code == 200
    assert resolved.json() == {"spotify_uri": URI}


def test_wrong_artist_is_not_accepted(spotify_responses: tuple[Mock, Mock]) -> None:
    _, get = spotify_responses
    get.return_value.json.return_value["tracks"]["items"][0]["artists"] = [
        {"name": "Cover Artist"}
    ]
    with TestClient(app) as client:
        response = client.post(
            "/spotify/resolve",
            json={
                "song_title": "Here Comes the Sun",
                "artist": "The Beatles",
                "market": "US",
            },
        )
    assert response.status_code == 404


def test_unplayable_result_is_not_accepted(
    spotify_responses: tuple[Mock, Mock],
) -> None:
    _, get = spotify_responses
    get.return_value.json.return_value["tracks"]["items"][0]["is_playable"] = False
    with TestClient(app) as client:
        response = client.post(
            "/spotify/resolve",
            json={
                "song_title": "Here Comes the Sun",
                "artist": "The Beatles",
                "market": "US",
            },
        )
    assert response.status_code == 404


def test_provider_failure_is_bad_gateway(
    spotify_responses: tuple[Mock, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        service.requests, "get", Mock(side_effect=requests.Timeout("timeout"))
    )
    with TestClient(app) as client:
        response = client.post(
            "/spotify/resolve",
            json={"song_title": "Song", "artist": "Artist", "market": "US"},
        )
    assert response.status_code == 502


def test_missing_credentials_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(service, "ENV_FILE", tmp_path / "absent.env")
    with TestClient(app) as client:
        response = client.post(
            "/spotify/resolve",
            json={"song_title": "Song", "artist": "Artist", "market": "US"},
        )
    assert response.status_code == 503


@pytest.mark.parametrize(
    "body",
    [
        {"song_title": "", "artist": "The Beatles", "market": "US"},
        {"song_title": "  ", "artist": "The Beatles", "market": "US"},
        {"song_title": "Song", "artist": "", "market": "US"},
        {"song_title": "Song", "artist": "Artist", "market": "USA"},
    ],
)
def test_invalid_request_is_rejected(body: dict[str, str]) -> None:
    with TestClient(app) as client:
        response = client.post("/spotify/resolve", json=body)
    assert response.status_code == 422
