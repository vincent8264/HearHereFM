"""Input and output contracts for a radio decision."""

from datetime import time as TimeOfDay
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

WeatherDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
NarrationText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
UserInput = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class PlayedMusic(BaseModel):
    mode: Literal["music"]
    song_title: ShortText
    artist: ShortText
    spotify_uri: str | None = Field(default=None, max_length=100)


class PlayedNarration(BaseModel):
    mode: Literal["narration"]
    text: NarrationText


type PlayedSection = Annotated[
    PlayedMusic | PlayedNarration, Field(discriminator="mode")
]


class RadioRequest(BaseModel):
    """Context for choosing and preparing the next playback section."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    weather: WeatherDescription
    time: TimeOfDay
    current_state: Literal["music", "narration"]
    played_history: list[PlayedSection] = Field(default_factory=list, max_length=10)
    user_input: UserInput | None = None


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
