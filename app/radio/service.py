"""Orchestrate one personal radio action."""

from app.radio.schemas import RadioAction, RadioRequest


def next_action(request: RadioRequest) -> RadioAction:
    """Select music or narration for the listener's current position."""
    # TODO: Fetch current weather for request.latitude and request.longitude.
    # TODO: Look up nearby places and retrieve factual source material.
    # TODO: Decide which mode to use, with structured output from the LLM.
    # TODO: In music mode, select a Spotify URI and start playback.
    # TODO: In narration mode, generate speech and return its audio URL.
    # TODO: Keep the two playback modes separate; never overlap their audio.
    raise NotImplementedError("Radio integrations are not configured yet")
