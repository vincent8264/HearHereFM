"""Input and output contracts for a radio decision."""

from datetime import time as TimeOfDay
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

WeatherDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class RadioRequest(BaseModel):
    """Context supplied when the current music or narration section ends."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    weather: WeatherDescription
    time: TimeOfDay
    current_state: Literal["music", "narration"]


class MusicAction(BaseModel):
    """A song selected for later Spotify resolution and playback."""

    mode: Literal["music"] = "music"
    song_title: str
    artist: str


class NarrationAction(BaseModel):
    """Text to send to the text-to-speech component."""

    mode: Literal["narration"] = "narration"
    text: str


type RadioAction = MusicAction | NarrationAction
