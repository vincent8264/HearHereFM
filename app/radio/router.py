"""HTTP routes for the personal radio feature."""

from fastapi import APIRouter, HTTPException

from app.radio.schemas import RadioAction, RadioRequest
from app.radio.service import next_action

router = APIRouter(prefix="/radio", tags=["radio"])


@router.post(
    "/next",
    response_model=RadioAction,
    responses={501: {"description": "Radio integrations are not configured yet"}},
)
def get_next_action(request: RadioRequest) -> RadioAction:
    """Request the next music or narration action."""
    try:
        return next_action(request)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
