"""Orchestrate one personal radio action."""

from app.places.service import PlaceLookupError, find_nearby_place
from app.radio.llm import choose_song, write_narration
from app.radio.schemas import RadioAction, RadioRequest


def next_action(request: RadioRequest) -> RadioAction:
    """Alternate sections and generate the content for the next one."""
    try:
        place = find_nearby_place(request.latitude, request.longitude)
    except PlaceLookupError:
        place = None
    if request.current_state == "music":
        return write_narration(request, place)
    return choose_song(request, place)
