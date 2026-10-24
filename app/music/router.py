
import os
import secrets
import hashlib
import base64
from urllib.parse import urlencode
import urllib.request
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from pydantic import BaseModel

from app.music.spotify_playback import (
    SpotifyPlayback,
    SpotifyPlaybackError,
)

router = APIRouter(prefix="/spotify", tags=["Spotify"])

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
REDIRECT_URI = "http://127.0.0.1:8000/spotify/callback"

# Local single-user demo only. Never expose tokens to the frontend.
oauth_pending = {}
spotify_tokens = {}


@router.get("/login")
def spotify_login():
    if not CLIENT_ID:
        raise HTTPException(500, "SPOTIFY_CLIENT_ID is missing")

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")

    state = secrets.token_urlsafe(24)
    oauth_pending[state] = verifier

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
        "scope": (
            "user-modify-playback-state "
            "user-read-playback-state"
        ),
    }

    url = "https://accounts.spotify.com/authorize?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/callback")
def spotify_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        raise HTTPException(400, f"Spotify authorization failed: {error}")

    verifier = oauth_pending.pop(state, None) if state else None

    if not code or not verifier:
        raise HTTPException(400, "Invalid Spotify callback or OAuth state")

    data = urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }).encode()

    request = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            tokens = json.load(response)
    except Exception:
        raise HTTPException(
            502, "Spotify token exchange failed; check server configuration"
        )

    spotify_tokens.clear()
    spotify_tokens.update(tokens)

    return {
        "status": "connected",
        "message": "Spotify authorization successful!",
        "scope": tokens.get("scope", ""),
    }


@router.get("/status")
def spotify_status():
    return {
        "connected": bool(spotify_tokens.get("access_token")),
        "note": "Tokens are stored temporarily in server memory",
    }


class PlayRequest(BaseModel):
    spotify_uri: str
    device_id: str | None = None


@router.post("/play")
def spotify_play(request: PlayRequest):
    # Access Token from the existing OAuth callback
    access_token = spotify_tokens.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Spotify not connected. Visit /spotify/login first.",
        )

    # Use the existing Spotify playback adapter
    player = SpotifyPlayback(access_token=access_token)

    try:
        result = player.play_track(
            track_uri=request.spotify_uri,
            device_id=request.device_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpotifyPlaybackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return result


@router.get("/devices")
def spotify_devices():
    import json
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError

    access_token = spotify_tokens.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Please login to Spotify first",
        )

    request = Request(
        "https://api.spotify.com/v1/me/player/devices",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        raise HTTPException(
            status_code=exc.code,
            detail=f"Spotify API returned {exc.code}",
        ) from exc

@router.get("/playback-state")
def get_playback_state():
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    import json

    token = spotify_tokens.get("access_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Spotify not connected",
        )

    request = Request(
        "https://api.spotify.com/v1/me/player",
        headers={"Authorization": f"Bearer {token}"},
    )

    try:
        with urlopen(request, timeout=10) as response:
            if response.status == 204:
                return {"active_device": False}

            data = json.load(response)

    except HTTPError as exc:
        raise HTTPException(
            status_code=exc.code,
            detail=f"Spotify API error: {exc.code}",
        ) from exc

    return {
        "is_playing": data.get("is_playing"),
        "track_name": (
            data.get("item") or {}
        ).get("name"),
        "track_uri": (
            data.get("item") or {}
        ).get("uri"),
        "device": (data.get("device") or {}).get("name"),
        "device_id": (data.get("device") or {}).get("id"),
    }