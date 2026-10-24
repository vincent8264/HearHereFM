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

    def _request(self, suffix: str = "", method: str = "GET") -> dict:
        request = Request(
            BASE + suffix,
            headers={"Authorization": f"Bearer {self.access_token}"},
            method=method,
        )
        try:
            with urlopen(request, timeout=10) as response:
                if response.status == 204 or method == "PUT":
                    return {}
                return json.load(response)
        except HTTPError as exc:
            raise SpotifyPlaybackError(
                f"Spotify returned HTTP {exc.code} for {method} playback control."
            ) from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise SpotifyPlaybackError("Could not control Spotify playback.") from exc

    def pause(self) -> dict[str, str]:
        self._request("/pause", "PUT")
        return {"status": "paused"}

    def devices(self) -> dict:
        return self._request("/devices")

    def state(self) -> dict:
        data = self._request()
        item = data.get("item") or {}
        device = data.get("device") or {}
        return {
            "active_device": bool(device),
            "is_playing": bool(data.get("is_playing")),
            "track_uri": item.get("uri"),
            "track_name": item.get("name"),
            "progress_ms": data.get("progress_ms") or 0,
            "duration_ms": item.get("duration_ms") or 0,
            "device": device.get("name"),
            "device_id": device.get("id"),
        }

    def play_track(
        self, track_uri: str, device_id: str | None = None
    ) -> dict[str, str]:
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
                    raise SpotifyPlaybackError(
                        f"Unexpected Spotify status: {response.status}"
                    )
        except HTTPError as exc:
            messages = {
                401: "Token invalid or expired: reauthorize/refresh token",
                403: "Forbidden: check Premium, permission scope, and policy",
                404: "No active Spotify playback device found",
                429: "Rate limited: retry later, respect Retry-After",
            }
            raise SpotifyPlaybackError(
                messages.get(exc.code, f"Spotify HTTP {exc.code}")
            ) from exc
        except URLError as exc:
            raise SpotifyPlaybackError("Cannot reach Spotify API") from exc
        return {"status": "command_accepted", "spotify_uri": track_uri}
