"""Offline tests: no real Spotify account or API call required."""

from unittest.mock import patch

import pytest

from app.music.spotify_playback import SpotifyPlayback


class FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_play_track_request():
    uri = "spotify:track:4iV5W9uYEdYUVa79Axb7Rh"
    with patch(
        "app.music.spotify_playback.urlopen", return_value=FakeResponse()
    ) as send:
        result = SpotifyPlayback("test-token").play_track(uri)
    request = send.call_args.args[0]
    assert request.get_method() == "PUT"
    assert request.full_url == "https://api.spotify.com/v1/me/player/play"
    assert request.get_header("Authorization") == "Bearer test-token"
    assert result == {"status": "command_accepted", "spotify_uri": uri}


def test_rejects_invalid_track_uri():
    with pytest.raises(ValueError):
        SpotifyPlayback("test-token").play_track("spotify:track:example")


def test_pause_reports_spotify_http_status():
    from urllib.error import HTTPError

    from app.music.spotify_playback import SpotifyPlaybackError

    with (
        patch(
            "app.music.spotify_playback.urlopen",
            side_effect=HTTPError(
                "https://api.spotify.com/v1/me/player/pause", 403, "Forbidden", {}, None
            ),
        ),
        pytest.raises(SpotifyPlaybackError, match="HTTP 403"),
    ):
        SpotifyPlayback("test-token").pause()


@pytest.mark.parametrize("status", [200, 204])
def test_pause_accepts_success_with_no_json_body(status):
    response = FakeResponse()
    response.status = status
    with patch("app.music.spotify_playback.urlopen", return_value=response):
        assert SpotifyPlayback("test-token").pause() == {"status": "paused"}
