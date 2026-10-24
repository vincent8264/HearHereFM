"""Input and output contracts for a radio decision."""

from typing import Literal

from pydantic import BaseModel, Field


class RadioRequest(BaseModel):
    """The listener's current position, supplied with their permission."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class MusicAction(BaseModel):
    """A Spotify track selected for the listener."""

    mode: Literal["music"] = "music"
    spotify_uri: str


class NarrationAction(BaseModel):
    """A spoken description of a nearby place."""

    mode: Literal["narration"] = "narration"
    place_name: str
    audio_url: str


type RadioAction = MusicAction | NarrationAction
