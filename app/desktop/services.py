"""Connect the desktop controller to existing providers and audio devices."""

import os
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from time import monotonic

from dotenv import dotenv_values

from app.desktop.audio import play_wav
from app.location_api.get_location import get_my_location
from app.music.router import get_player, is_connected
from app.music.spotify_playback import SpotifyPlaybackError
from app.radio.schemas import MusicAction, RadioAction, RadioRequest
from app.radio.service import next_action
from app.spotify.service import resolve_song
from app.tts.service import get_tts_service
from app.voice.microphone import capture_text
from app.weather_api.service import get_weather

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class PreparedSection:
    action: RadioAction
    uri: str | None = None
    audio_path: Path | None = None


class DesktopServices:
    def __init__(self) -> None:
        self._location: tuple[float, float] | None = None
        self._weather: dict | None = None
        self._weather_at = 0.0
        self._prompt: Path | None = None

    def ensure_ready(self) -> None:
        if not is_connected():
            raise SpotifyPlaybackError(
                "Connect Spotify at /spotify/login before starting radio."
            )

    def pause(self) -> None:
        if is_connected():
            player = get_player()
            state = player.state()
            if (
                state["is_playing"]
                and "web player" in (state.get("device") or "").casefold()
            ):
                player.pause()

    def prompt(self, cancel: Event) -> bool:
        if self._prompt is None or not self._prompt.is_file():
            service = get_tts_service()
            filename = service.synthesize("Tell me what you would like to hear.")
            self._prompt = service.audio_dir / filename
        return play_wav(self._prompt, cancel)

    def capture(self, cancel: Event) -> str:
        return capture_text(cancel_event=cancel)

    def error_notice(self, cancel: Event) -> None:
        service = get_tts_service()
        filename = service.synthesize(
            "The radio could not continue. Please check the setup and try again."
        )
        play_wav(service.audio_dir / filename, cancel)

    def context(self) -> dict:
        env = dotenv_values(ENV_FILE, interpolate=False)
        try:
            if self._location is None:
                latitude = os.getenv("RADIO_LATITUDE") or env.get("RADIO_LATITUDE")
                longitude = os.getenv("RADIO_LONGITUDE") or env.get("RADIO_LONGITUDE")
                if latitude is not None and longitude is not None:
                    self._location = (float(latitude), float(longitude))
                else:
                    location = get_my_location()
                    self._location = (
                        float(location["latitude"]),
                        float(location["longitude"]),
                    )
            if self._weather is None or monotonic() - self._weather_at >= 300:
                self._weather = get_weather(*self._location)
                self._weather_at = monotonic()
            weather = self._weather
            return {
                "latitude": self._location[0],
                "longitude": self._location[1],
                "weather": f"{weather['temperature_f']} F; rain {weather['rain_in']} inches; precipitation {weather['precipitation_in']} inches",
                "time": weather["time"].split("T")[1][:5],
            }
        except Exception as exc:
            raise RuntimeError(
                "Could not fetch location/weather. Check connectivity or RADIO_LATITUDE/RADIO_LONGITUDE."
            ) from exc

    def prepare(self, request: RadioRequest) -> PreparedSection:
        action = next_action(request)
        if action.mode == "narration":
            service = get_tts_service()
            filename = service.synthesize(action.text)
            return PreparedSection(action, audio_path=service.audio_dir / filename)
        env = dotenv_values(ENV_FILE, interpolate=False)
        market = os.getenv("SPOTIFY_MARKET") or env.get("SPOTIFY_MARKET") or "US"
        uri = resolve_song(
            action.song_title,
            action.artist,
            market,
            access_token=get_player().access_token,
        )
        if any(
            section.mode == "music" and section.spotify_uri == uri
            for section in request.played_history
        ):
            raise RuntimeError(
                "Spotify resolved a track already played. Activate again to request another song."
            )
        return PreparedSection(action, uri=uri)

    def start_music(self, section: PreparedSection, cancel: Event) -> bool:
        if not isinstance(section.action, MusicAction) or section.uri is None:
            raise ValueError("Music is missing its resolved Spotify URI.")
        env = dotenv_values(ENV_FILE, interpolate=False)
        player = get_player()
        device_id = os.getenv("SPOTIFY_DEVICE_ID") or env.get("SPOTIFY_DEVICE_ID")
        devices = [
            item
            for item in player.devices().get("devices", [])
            if "web player" in item.get("name", "").casefold()
            and not item.get("is_restricted")
            and item.get("id")
        ]
        if device_id:
            device = next((item for item in devices if item["id"] == device_id), None)
        else:
            device = next((item for item in devices if item.get("is_active")), None)
            if device is None:
                device = next(iter(devices), None)
        if device is None:
            raise SpotifyPlaybackError(
                "Open Spotify Web Player in your browser and play a song once first."
            )
        device_id = device["id"]
        if cancel.is_set():
            return False
        player.play_track(section.uri, device_id)
        deadline = monotonic() + 8
        while not cancel.is_set() and monotonic() < deadline:
            state = get_player().state()
            if (
                state["track_uri"] == section.uri
                and state["is_playing"]
                and state["device_id"] == device_id
            ):
                return True
            cancel.wait(0.25)
        if cancel.is_set():
            return False
        raise SpotifyPlaybackError(
            "Spotify did not confirm playback on the selected device."
        )

    def wait_music(self, section: PreparedSection, cancel: Event) -> bool:
        remaining = None
        checked_at = monotonic()
        while not cancel.is_set():
            state = get_player().state()
            if (
                state["is_playing"]
                and "web player" not in (state.get("device") or "").casefold()
            ):
                raise SpotifyPlaybackError("Playback switched away from Web Player.")
            if state["track_uri"] != section.uri or not state["is_playing"]:
                if remaining is not None and (
                    remaining <= 2500
                    or (monotonic() - checked_at) * 1000 >= remaining - 1000
                ):
                    self.pause()
                    return True
                raise SpotifyPlaybackError(
                    "Spotify playback was paused or changed outside the radio."
                )
            remaining = state["duration_ms"] - state["progress_ms"]
            checked_at = monotonic()
            if state["duration_ms"] <= 0:
                raise SpotifyPlaybackError(
                    "Spotify did not return a usable track duration."
                )
            if remaining <= 1500:
                if cancel.wait(max(0, remaining / 1000)):
                    return False
                self.pause()
                return True
            cancel.wait(min(2, max(0.1, remaining / 1000 - 1)))
        return False

    def play_narration(
        self, section: PreparedSection, cancel: Event, on_started
    ) -> bool:
        if section.audio_path is None:
            raise ValueError("Narration audio is missing.")
        self.pause()
        return play_wav(section.audio_path, cancel, on_started)
