"""Standalone Spotify Connect control adapter for authorized, compliant use.

Does not acquire or store OAuth tokens. Do not pass tokens to an LLM.
"""

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TRACK_URI_RE = re.compile(r"^spotify:track:[A-Za-z0-9]{22}$")
BASE = "https://api.spotify.com/v1/me/player"


class SpotifyPlaybackError(RuntimeError):
    """Spotify rejected the playback command or was unreachable."""


@dataclass(frozen=True)
class SpotifyPlayback:
    """API adapter. OAuth access token must have user-modify-playback-state."""

    access_token: str

    def play_track(self, track_uri: str, device_id: str | None = None) -> dict[str, str]:
        """Request a licensed Spotify client to play one track.

        Successful response means command accepted, not confirmed audible output.
        """
        if not TRACK_URI_RE.fullmatch(track_uri):
            raise ValueError("Expected a valid spotify:track:<22-character ID> URI")
        if not self.access_token:
            raise ValueError("Spotify OAuth access token is required")
        params = urlencode({"device_id": device_id}) if device_id else ""
        url = f"{BASE}/play" + (f"?{params}" if params else "")
        payload = json.dumps({"uris": [track_uri]}).encode("utf-8")
        request = Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 204:
                    raise SpotifyPlaybackError(f"Unexpected Spotify status: {response.status}")
        except HTTPError as exc:
            messages = {
                401: "Token invalid or expired: reauthorize/refresh token",
                403: "Forbidden: check Premium, permission scope, and policy",
                404: "No active Spotify playback device found",
                429: "Rate limited: retry later, respect Retry-After",
            }
            raise SpotifyPlaybackError(messages.get(exc.code, f"Spotify HTTP {exc.code}")) from exc
        except URLError as exc:
            raise SpotifyPlaybackError("Cannot reach Spotify API") from exc
        return {"status": "command_accepted", "spotify_uri": track_uri}
