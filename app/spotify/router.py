"""HTTP endpoint for resolving a song suggestion to a Spotify URI."""

from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from app.music.router import get_player, is_connected
from app.music.spotify_playback import SpotifyPlaybackError
from app.spotify.service import (
    SpotifyConfigurationError,
    SpotifyLookupError,
    SpotifyNoMatchError,
    resolve_song,
)

router = APIRouter(prefix="/spotify", tags=["spotify"])
SongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ResolveRequest(BaseModel):
    song_title: SongText = Field(max_length=200)
    artist: SongText = Field(max_length=200)
    market: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class ResolveResponse(BaseModel):
    spotify_uri: str


@router.post(
    "/resolve",
    response_model=ResolveResponse,
    responses={
        404: {"description": "No matching Spotify track was found"},
        502: {"description": "Spotify catalog lookup failed"},
        503: {"description": "Spotify app credentials are not configured"},
    },
)
def resolve(request: ResolveRequest) -> ResolveResponse:
    """Convert an LLM song suggestion to a verified Spotify catalog URI."""
    try:
        token = get_player().access_token if is_connected() else None
        uri = resolve_song(
            request.song_title, request.artist, request.market, access_token=token
        )
    except SpotifyConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpotifyLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SpotifyPlaybackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SpotifyNoMatchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ResolveResponse(spotify_uri=uri)
