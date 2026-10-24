"""HTTP routes for the personal radio feature."""

from fastapi import APIRouter, HTTPException

from app.radio.llm import LLMConfigurationError, LLMGenerationError
from app.radio.schemas import RadioAction, RadioRequest
from app.radio.service import next_action

router = APIRouter(prefix="/radio", tags=["radio"])


@router.post(
    "/next",
    response_model=RadioAction,
    responses={
        502: {"description": "The model could not generate a valid radio action"},
        503: {"description": "The OpenAI API key is not configured"},
    },
)
def get_next_action(request: RadioRequest) -> RadioAction:
    """Request the next music or narration action."""
    try:
        return next_action(request)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
