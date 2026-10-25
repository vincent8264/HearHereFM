"""Orchestrate one personal radio action."""

import re
from difflib import SequenceMatcher

from app.places.service import PlaceLookupError, find_nearby_place
from app.radio.llm import LLMGenerationError, choose_action
from app.radio.schemas import RadioAction, RadioRequest


def _song_key(title: str, artist: str) -> tuple[str, str]:
    return (
        " ".join(re.findall(r"\w+", title.casefold())),
        " ".join(re.findall(r"\w+", artist.casefold())),
    )


def _music_streak(request: RadioRequest) -> int:
    if request.current_state != "music":
        return 0
    streak = 0
    for section in reversed(request.played_history):
        if section.mode != "music":
            break
        streak += 1
    return streak or 1


def _rejection_reason(action: RadioAction, request: RadioRequest) -> str | None:
    if action.mode == "music":
        if _music_streak(request) >= 3:
            return "Choose narration after three consecutive songs."
        song_key = _song_key(action.song_title, action.artist)
        if any(
            section.mode == "music"
            and _song_key(section.song_title, section.artist) == song_key
            for section in request.played_history
        ):
            return "That song already played. Choose a different song."
    else:
        text = " ".join(action.text.casefold().split())
        if any(
            section.mode == "narration"
            and SequenceMatcher(
                None, text, " ".join(section.text.casefold().split())
            ).ratio()
            >= 0.9
            for section in request.played_history
        ):
            return (
                "That narration is too similar to a previous script. Write a fresh one."
            )
    return None


def next_action(
    request: RadioRequest, *, retry_reason: str | None = None
) -> RadioAction:
    """Let the model choose a section, then enforce variety."""
    try:
        place = find_nearby_place(request.latitude, request.longitude)
    except PlaceLookupError:
        place = None
    for _ in range(2):
        action = choose_action(request, place, retry_reason=retry_reason)
        retry_reason = _rejection_reason(action, request)
        if retry_reason is None:
            return action
    raise LLMGenerationError("The model could not choose a non-repetitive action")
