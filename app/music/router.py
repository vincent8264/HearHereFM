"""Single-user desktop OAuth and Spotify Connect control."""

import base64
import hashlib
import os
import secrets
from pathlib import Path
from threading import RLock
from time import time
from urllib.parse import urlencode

import requests
from dotenv import dotenv_values
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.music.spotify_playback import SpotifyPlayback, SpotifyPlaybackError

router = APIRouter(prefix="/spotify", tags=["spotify-playback"])
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
TOKEN_URL = "https://accounts.spotify.com/api/token"
oauth_pending: dict[str, tuple[str, float]] = {}
spotify_tokens: dict = {}
_lock = RLock()


def _config(name: str, default: str = "") -> str:
    return (
        os.getenv(name)
        or dotenv_values(ENV_FILE, interpolate=False).get(name)
        or default
    )


def _token_request(data: dict[str, str]) -> dict:
    try:
        response = requests.post(TOKEN_URL, data=data, timeout=15)
        response.raise_for_status()
        tokens = response.json()
        if (
            not isinstance(tokens.get("access_token"), str)
            or not tokens["access_token"]
        ):
            raise ValueError("Missing access token")
        tokens["expires_at"] = time() + float(tokens["expires_in"])
        return tokens
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        raise SpotifyPlaybackError(
            "Spotify authorization failed. Reconnect Spotify."
        ) from exc


def get_player() -> SpotifyPlayback:
    """Refresh expiring credentials; never include tokens in public responses."""
    with _lock:
        if not spotify_tokens.get("access_token"):
            raise SpotifyPlaybackError(
                "Spotify is not connected. Open /spotify/login once."
            )
        if spotify_tokens.get("expires_at", 0) <= time() + 30:
            refresh = spotify_tokens.get("refresh_token")
            if not refresh:
                raise SpotifyPlaybackError("Spotify login expired. Reconnect Spotify.")
            tokens = _token_request(
                {
                    "client_id": _config("SPOTIFY_CLIENT_ID"),
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                }
            )
            tokens.setdefault("refresh_token", refresh)
            spotify_tokens.update(tokens)
        return SpotifyPlayback(spotify_tokens["access_token"])


def is_connected() -> bool:
    with _lock:
        return bool(spotify_tokens.get("access_token"))


@router.get("/login")
def spotify_login() -> RedirectResponse:
    client_id = _config("SPOTIFY_CLIENT_ID")
    if not client_id:
        raise HTTPException(503, "SPOTIFY_CLIENT_ID is not configured")
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_urlsafe(24)
    with _lock:
        expired = [
            key for key, (_, expiry) in oauth_pending.items() if expiry <= time()
        ]
        for key in expired:
            del oauth_pending[key]
        if len(oauth_pending) >= 20:
            raise HTTPException(429, "Too many pending Spotify logins")
        oauth_pending[state] = (verifier, time() + 600)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": _config(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/spotify/callback"
        ),
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
        "scope": "user-modify-playback-state user-read-playback-state",
    }
    return RedirectResponse(
        "https://accounts.spotify.com/authorize?" + urlencode(params)
    )


@router.get("/callback")
def spotify_callback(
    code: str | None = None, state: str | None = None, error: str | None = None
) -> dict[str, str]:
    with _lock:
        pending = oauth_pending.pop(state, None) if state else None
    if error or not code or pending is None or pending[1] <= time():
        raise HTTPException(400, "Invalid or expired Spotify authorization")
    try:
        tokens = _token_request(
            {
                "client_id": _config("SPOTIFY_CLIENT_ID"),
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": pending[0],
                "redirect_uri": _config(
                    "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/spotify/callback"
                ),
            }
        )
    except SpotifyPlaybackError as exc:
        raise HTTPException(502, detail=str(exc)) from exc
    with _lock:
        spotify_tokens.clear()
        spotify_tokens.update(tokens)
    return {"status": "connected"}


@router.get("/status")
def spotify_status() -> dict[str, bool]:
    return {"connected": is_connected()}


class PlayRequest(BaseModel):
    spotify_uri: str
    device_id: str | None = Field(default=None, max_length=200)


def _run_player(method: str, **kwargs) -> dict:
    try:
        return getattr(get_player(), method)(**kwargs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except SpotifyPlaybackError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/play")
def spotify_play(request: PlayRequest) -> dict:
    return _run_player(
        "play_track", track_uri=request.spotify_uri, device_id=request.device_id
    )


@router.post("/pause")
def spotify_pause() -> dict:
    return _run_player("pause")


@router.get("/devices")
def spotify_devices() -> dict:
    return _run_player("devices")


@router.get("/playback-state")
def get_playback_state() -> dict:
    return _run_player("state")
