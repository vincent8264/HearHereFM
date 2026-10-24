"""Resolve a model-suggested song to a Spotify track URI."""

import os
import re
import unicodedata
from pathlib import Path

import requests
from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"
TRACK_URI = re.compile(r"spotify:track:[A-Za-z0-9]{22}\Z")


class SpotifyConfigurationError(Exception):
    """Spotify app credentials are missing."""


class SpotifyLookupError(Exception):
    """Spotify could not complete a catalog lookup."""


class SpotifyNoMatchError(Exception):
    """No search result matched both the requested song and artist."""


def _normalize(value: str) -> str:
    ascii_text = "".join(
        char
        for char in unicodedata.normalize(
            "NFKD", value.casefold().replace("&", " and ")
        )
        if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"\w+", ascii_text))


def _matches(track: object, title: str, artist: str) -> bool:
    if not isinstance(track, dict):
        return False
    name, artists, uri = track.get("name"), track.get("artists"), track.get("uri")
    if not isinstance(name, str) or not isinstance(artists, list):
        return False
    if not isinstance(uri, str) or TRACK_URI.fullmatch(uri) is None:
        return False
    if track.get("is_playable") is False:
        return False
    wanted_title = _normalize(title)
    found_title = _normalize(name)
    title_matches = found_title == wanted_title or (
        found_title.startswith(wanted_title + " ")
        and any(
            word in found_title[len(wanted_title) :] for word in ("remaster", "mix")
        )
    )
    artist_matches = any(
        isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and _normalize(entry["name"]) == _normalize(artist)
        for entry in artists
    )
    return title_matches and artist_matches


def resolve_song(
    title: str, artist: str, market: str, *, access_token: str | None = None
) -> str:
    """Find the requested recording in a market and return its track URI."""
    env = dotenv_values(ENV_FILE, interpolate=False)
    client_id = os.getenv("SPOTIFY_CLIENT_ID") or env.get("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET") or env.get(
        "SPOTIFY_CLIENT_SECRET"
    )
    if not access_token and (not client_id or not client_secret):
        raise SpotifyConfigurationError("Spotify app credentials are not configured")

    search_title = title.replace('"', "")
    search_artist = artist.replace('"', "")
    try:
        if access_token is None:
            token_response = requests.post(
                TOKEN_URL,
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
                timeout=10,
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("Missing Spotify access token")

        queries = (
            f'track:"{search_title}" artist:"{search_artist}"',
            f'track:"{search_title}"',
        )
        for query in queries:
            search_response = requests.get(
                SEARCH_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": query, "type": "track", "limit": 10, "market": market},
                timeout=10,
            )
            search_response.raise_for_status()
            tracks = search_response.json()["tracks"]["items"]
            if not isinstance(tracks, list):
                raise TypeError("Invalid Spotify search results")
            for track in tracks:
                if _matches(track, title, artist):
                    return track["uri"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise SpotifyLookupError("Could not search Spotify") from exc

    raise SpotifyNoMatchError("No matching Spotify track was found")
