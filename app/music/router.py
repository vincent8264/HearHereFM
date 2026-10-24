
import os
import secrets
import hashlib
import base64
from urllib.parse import urlencode
import urllib.request
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

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
