"""Expose current weather through the shared FastAPI application."""

import requests
from fastapi import APIRouter, HTTPException, Query

from .service import get_weather

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("")
def fetch_weather(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
) -> dict[str, float | str]:
    try:
        return get_weather(latitude, longitude)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve weather.",
        ) from exc
