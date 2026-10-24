from fastapi import APIRouter, HTTPException, Query

from .service import get_weather

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("")
def fetch_weather(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    try:
        return get_weather(latitude, longitude)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to retrieve weather: {str(e)}",
        ) from e