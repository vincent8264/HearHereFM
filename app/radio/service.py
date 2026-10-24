"""Orchestrate one personal radio action."""

from app.radio.llm import choose_song, write_narration
from app.radio.schemas import RadioAction, RadioRequest


def next_action(request: RadioRequest) -> RadioAction:
    """Alternate sections and generate the content for the next one."""
    if request.current_state == "music":
        return write_narration(request)
    return choose_song(request)
